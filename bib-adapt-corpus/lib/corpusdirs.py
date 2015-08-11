#! /usr/bin/python3
"""
Common corpus management
"""

from glob            import glob
from os              import mkdir, path
from shutil          import rmtree, move
from re              import match, search, sub, escape, MULTILINE
from csv             import DictReader
from collections     import defaultdict
from subprocess      import call
from configparser    import ConfigParser

# ----------------------------------------------------------------------
# read-in global config values (workshop dirs, api conf, grobid home)
GCONF = ConfigParser()

# default location: ./global_conf.ini (relative to corpus.py)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, 'global_conf.ini')
conf_file = open(conf_path, 'r')
GCONF.read_file(conf_file)
conf_file.close()
# ----------------------------------------------------------------------
# Globals

# Structure de corpus étendue ("shelf" pour "étagère")
SHELF_STRUCT = {
	# basic set --------------------------------------
	'PDF0' : {'d':'A-pdfs',       'ext':'.pdf'},
	'XMLN' : {'d':'B-xmlnatifs',  'ext':'.xml'},
	'GTEI' : {'d':'C-goldxmltei', 'ext':'.tei.xml'},
	# ------------------------------------------------
	
	# bibzone = segmentation -------------------------
	'BZRTX': {'d':  'D.1.a-trainers-bibzone_rawtxt',
			  'ext':'.training.segmentation.rawtxt',
			},
	'BZRTK': {'d':  'D.1.b-trainers-bibzone_rawtok',
			  'ext':'.training.segmentation',
			  'tgt':['segmentation','corpus','raw']
			},
	'BZTEI': {'d':  'D.1.z-trainers-bibzone_tei',
			  'ext':'.training.segmentation.tei.xml',
			  'tgt':['segmentation','corpus','tei']
			},
	
	# biblines = referenceSegmentation ---------------
	'BLRTX': {'d':  'D.2.a-trainers-biblines_rawtxt',
			  'ext':'.training.referenceSegmenter.rawtxt',
			},
	'BLRTK': {'d':  'D.2.b-trainers-biblines_rawtok',
			  'ext':'.training.referenceSegmenter',
			  'tgt':['reference-segmenter','corpus','raw']
			},
	'BLTEI': {'d':  'D.2.z-trainers-biblines_tei',
			  'ext':'.training.referenceSegmenter.tei.xml',
			  'tgt':['reference-segmenter','corpus','tei']
			},
	
	# bibfields = citations --------------------------
	'BFRTX': {'d':  'D.3.a-trainers-bibfields_rawtxt',
			  'ext':'.training.references.rawtxt',
			},
	'BFTEI': {'d':  'D.3.z-trainers-bibfields_tei', 
			  'ext':'.training.references.tei.xml',
			  'tgt':['citation','corpus']
			},
	
	# authornames = citations --------------------------
	'AURTX': {'d':  'D.4.a-trainers-authornames_rawtxt', 
			  'ext':'.training.citations.authors.rawtxt',
			},
	'AUTEI': {'d':  'D.4.z-trainers-authornames_tei', 
			  'ext':'.training.citations.authors.tei.xml',
			  'tgt':['name', 'citation','corpus']
			},
	}
# NB:relations attendues par grobid entre les extensions dans D-trainers
#     '.XXX' pour les rawtoks implique automatiquement:
#     '.XXX.rawtxt' pour les rawtxt
#     '.XXX.tei.xml pour les tei d'entrainement

class Corpus:
	"""
	A collection of docs with their metadata
	and their diverse input text formats.
	
	Usual slots:

	 -self.meta
	 -self.shelfs
	
	2nd step
	 -self.cols
	 -self.fileids
	"""
	# TODO absolument une dir extraite de s1 sous la forme read_dir
	def __init__(self, ko_name, new_infos=None, read_dir=False):
		"""
		IN: new_infos : a metadata table (eg sampler output)
		                (no fulltexts yet, no workdir needed)
		
		or in read mode:
		IN: read_dir : path to an existing Corpus dir
		              (with data/ and meta/ subdirs, etc.)
		
		OUT: Corpus instance with:
			self.bnames
			-----------
			   =  basenames created for each file (from new_infos[id])
			
			self.shelfs
			-----------
			   ~ structured persistance layers (currently fs based)
			   => provides shelfs subdir, file ext and fileids(shname)
			
			and also: self.meta    self.cols     self.name     self.cdir
			          ---------    ---------     ---------     ---------
		"""
		
		# VAR 1: >> name << almost free except should be usable in a fs
		if type(ko_name) == str and match(r'^[\w-]+$', ko_name):
			self.name = ko_name
		else:
			raise TypeError("new Corpus() needs a name str matching /^[0-9A-Za-z_-]+$/ as 1st arg")
		
		# VAR 2: **cdir** new dir for this corpus and subdirs ----------
		conf = GCONF['workshop']
		root_corpora_dir = path.join(conf['HOME'],conf['CORPUS_HOME'])

		if not read_dir:
			self.cdir = path.join(root_corpora_dir, ko_name)
			mkdir(self.cdir)
			mkdir(self.cdir+"/data")    # pour les documents
			mkdir(self.cdir+"/meta")    # pour les tables etc.
		else:
			# remove any trailing slash
			read_dir = sub(r'/+$', '', read_dir)
			read_root, read_subdir = path.split(read_dir)
			if not len(read_root):
				read_root='.'
			
			# check correct corpora dir
			if not path.samefile(read_root, root_corpora_dir):
				print("WARN: reading a corpus in dir '%s' instead of default '%s'"
				      % (read_root, root_corpora_dir) )
			
			# check correct corpus dir name
			if read_subdir != ko_name:
				raise TypeError("""ERROR -- Corpus(__init__ from dir): 
				=> corpus name '%s' should be same as your dir %s <="""
				 % (ko_name, read_subdir) )
			else:
				self.cdir = read_dir
				
				# read corresponding infos
				infos_path = path.join(self.cdir,'meta','infos.tab')
				fi = open(infos_path,'r')
				new_infos = fi.readlines()
				fi.close()
			
			print("DID READ INFOS FROM %s" % infos_path)

		# VARS 3 and 4: >> meta << and >> cols << lookup tables --------
		if new_infos:
			# a simple csv reader (headers as in sampler.STD_MAP)
			records_obj = DictReader(new_infos, delimiter='\t')
			
			# required headers: istex_id, corpus
			
			# ----- metadata
			# meta: table where each rec 
			#       is a dict with always
			#       the same keys
			self.meta = [rec for rec in records_obj]
			
			# cols: same but transposed 
			#       for column access
			self.cols = self._read_columns()
			
			# ----- fileids
			# VARS 5: >> bnames << basenames for persistance slots
			my_ids = self.cols['istex_id']
			my_lot = self.cols['corpus']
			self.bnames = []
			for i,did in enumerate(my_ids):
				self.bnames.append(my_lot[i]+'-'+did)
			
			# all saved files pertaining to the same document object
			# will thus share the same basename, with a different .ext
			# usage: [id+lot =>] basenames [=> fileids == fspaths]
			
			if not read_dir:
				# for "human" access SAVE infos to filesystem > $cdir/meta/.
				tab_fh = open(path.join(self.cdir,'meta','infos.tab'),'w')
				tab_fh.write("\n".join(new_infos) + "\n")
				tab_fh.close()
				bn_fh = open(path.join(self.cdir,'meta','basenames.ls'),'w')
				bn_fh.write("\n".join(self.bnames) + "\n")
				bn_fh.close()
		
		else:
			self.meta = None
			self.cols = None
			self.bnames = None
		
		# VAR 7: >> shelfs <<   (index de flags pour "sous-dossiers par format")
		#                           shelfs refer to dirs of docs
		#                           of a given format
		self.shelfs = {}
		
		if read_dir:
			# initialize shelfs from subdir presence
			for shname in SHELF_STRUCT:
				if path.exists(self.shelf_path(shname)):
					self.shelfs[shname] = True
				else:
					self.shelfs[shname] = False
		else:
			# initialize empty
			for shname in SHELF_STRUCT:
				self.shelfs[shname] = False
				# ex: {
				# 	'PDF0' : False,       # later: self.shelf[shname] to True
				# 	'NXML' : False,       # if and only if the fulltext files
				# 	'GTEI' : False,       # have already been placed in their
				# }                      # appropriate subdir
	
	def shelf_path(self, my_shelf):
		"""
		Returns the standard dir for a shelf: 
		   >> $cdir/data/$shsubdir <<
		(it contains the files of a given format)
		"""
		if my_shelf in SHELF_STRUCT:
			shsubdir = SHELF_STRUCT[my_shelf]['d']
			shpath = path.join(self.cdir, 'data', shsubdir)
			return shpath
		else:
			return None
	
	# TODO, si on en veut qu'un, c'est un peu dommage de les faire tous...
	def fileids(self, my_shelf=None):
		if my_shelf:
			if my_shelf in SHELF_STRUCT:
				# file extension
				shext = SHELF_STRUCT[my_shelf]['ext']
				# standard shelf dir
				shpath = self.shelf_path(my_shelf)
				return [path.join(shpath, bn+shext) for bn in self.bnames]
			else:
				print("WARN: Unknown shelf type %s" % my_shelf)
				return None
		else:
			return self.bnames
	
	def _read_columns(self):
		"""
		Function for index transposition (used in __init__: self.cols)
		Records are an array of dicts, that all have the same keys 
		(info lines)
		We return a dict of arrays, that all have the same length.
		(=> info columns)
		"""
		records = self.meta
		cols = defaultdict(list)
		try:
			for this_col in records[0].keys():
				colarray = [rec_i[this_col] for rec_i in records]
				cols[this_col] = colarray
		except IndexError as e:
			raise(TypeError('Each record in the input array must contain same keys (aka "column names")'))
		return cols
	
	def assert_fulltexts(self, shname):
		"""
		Just sets the shelf flag to true
		(we assume the files have been put there)
		(and the fileids are automatically known from bnames + shelf_struct)
		"""
		if shname in SHELF_STRUCT:
			self.shelfs[shname] = True
	
	def fulltextsh(self):
		"""
		The list of present fulltexts shelves.
		"""
		return [sh for sh, bol in self.shelfs.items() if bol]
	
	def dtd_repair(self, dtd_prefix=None):
		"""
		Linking des dtd vers nos dtd stockées dans /etc
		ou dans un éventuel autre dossier dtd_prefix
		"""
		if not dtd_prefix:
			our_root = GCONF['workshop']['HOME']
			dtd_subdir = GCONF['workshop']['CORPUS_DTDS']
			dtd_prefix = path.join(our_root,dtd_subdir)
			
			print("TGT DTD PREFIX:", dtd_prefix)
			
		# ssi dossier natif présent
		if self.shelfs['XMLN']:
			todofiles = self.fileids(my_shelf="XMLN")
			
			# temporary output_dir
			output_dir = path.join(self.cdir, "tempdtd")
			mkdir(output_dir)
			
			for fi in todofiles:
				fh = open(fi, 'r')
				long_str = fh.read()
				fh.close()
				
				m = search(
				  # splits a doctype declaration in 3 elements
				  # lhs + '"' + uri.dtd + '"' + rhs
				  r'(<!DOCTYPE[^>]+(?:PUBLIC|SYSTEM)[^>]*)"([^"]+\.dtd)"((?:\[[^\]]*\])?[^>]*>)',
				  long_str, MULTILINE)
				
				if m:
					# kept for later
					left_hand_side = m.groups()[0]
					right_hand_side = m.groups()[2]
					
					# replace the middle group uri with our prefix + old dtd_basename
					dtd_uri = m.groups()[1]
					# print ('FOUND:' + dtd_uri)
					dtd_basename = path.basename(dtd_uri)
					new_dtd_path = dtd_prefix + '/' + dtd_basename
					
					# print(new_dtd_path)
					
					# substitute a posteriori
					original_declaration = left_hand_side+'"'+dtd_uri+'"'+right_hand_side
					new_declaration = left_hand_side+'"'+new_dtd_path+'"'+right_hand_side
					new_str = sub(escape(original_declaration), new_declaration, long_str)
					
					# save
					filename = path.basename(fi)
					outfile = open(output_dir+'/'+filename, 'w')
					outfile.write(new_str)
					outfile.close()
				else:
					if not search(r'wiley', long_str):
						# wiley often has no DTD declaration, just ns
						print('dtd_repair:no match on %s' % fi)
					# save as is
					filename = path.basename(fi)
					outfile = open(output_dir+'/'+filename, 'w')
					outfile.write(long_str)
					outfile.close()
			
			# remove previous and rename to std dir
			orig_dir = self.shelf_path("XMLN")
			rmtree(orig_dir)
			move(output_dir, orig_dir)


	def pub2tei(self, bibl_type=None, p2t_lib=None):
		"""
		Appel d'une transformation XSLT 2.0 Pub2TEI
		
		actuellement via appel système à saxonb-xslt
		(renvoie 0 si tout est ok et 2 s'il n'y a eu ne serait-ce qu'une erreur)
		"""
		if not p2t_lib:
			our_root = GCONF['workshop']['HOME']
			pd2_lib = GCONF['workshop']['PUB2TEI_XSL']
			pd2_path = path.join(our_root,pd2_lib,'Stylesheets','Publishers.xsl')
		
		# si dossier d'entrée
		if self.shelfs['XMLN']:
			xml_dirpath = self.shelf_path("XMLN")
			gtei_dirpath = self.shelf_path("GTEI")
			
			# mdkir dossier de sortie
			if not path.exists(gtei_dirpath):
				mkdir(gtei_dirpath)
			
			call_args = [
			"saxonb-xslt", 
			"-xsl:%s" % path.join(pd2_lib,'Stylesheets','Publishers.xsl'),
			"-s:%s" % xml_dirpath,
			"-o:%s" % gtei_dirpath
			]
			
			# subprocess.call -----
			retval= call(call_args)
		return retval


	# ------------------------------------------------------------------
	# PREP_TO_SHELVES = instructions de corpus.grobid_create_training()

	# grobid_create_training implique naturellement un traitement commun
	# mais les accès ensuite et l'usage des documents seront distincts..

	# /!\ les sh_tgt pour bibfields et authornames ne donnent pas de txt
	#     on le créera depuis les tei de prépa => £TODO modif grobid

	# /!\ dans ts les cas on ne conserve pas les tei de prépa (non gold)
	#     => n'apparaissent pas dans sh_tgt
	PREP_TO_SHELVES = {
		'bibzone': {'prep_exe':  'createTrainingSegmentation',
					'tgt_shelves': ['BZRTX','BZRTK'],
				   },

		'biblines': {'prep_exe': 'createTrainingReferenceSegmentation',
					'tgt_shelves': ['BLRTX','BLRTK'],
				   },

		'bibfields': {'prep_exe': 'createTrainingFulltext',
					# 'tgt_shelves' :   ['BFRTX'], # idéalement modif GB
					
					# autrement "hack" pour obtenir BFRTX
					'tgt_shelves' :   [],
					'sh_mktxt': {'from':'BFTEI', 'to':'BFRTX'},
				   },

		'authornames': {'prep_exe': 'createTrainingFulltext', 
					# 'tgt_shelves' :   ['AURTX'], # idéalement modif GB
					
					# autrement "hack" pour obtenir AURTX
					'tgt_shelves' :   [],
					'sh_mktxt': {'from':'AUTEI', 'to':'AURTX'},
				   },
		}

	# todo skip if (wiley or nature) and (bibfields ou authornames)
	def grobid_create_training(self, tgt_model):
		"""
		Appel de grobid createTraining (pour les rawtoks et les rawtxts)
		
		Les instructions de traitement sont :
		  - la liste des modèles à faire pour grobid
		  - un dic PREP_TO_SHELVES aux entrées de la forme:
		
		'nom_modele':{'prep_exe': commande grobid,
		              'tgt_shelves' : [étagères à récupérer],
		              },
		
		cf. aussi grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/
		    sous "Generation of training data"
		
		hack : une clé supplémentaire 
		       'sh_mktxt': pointe une étagère permettant de refaire le texte
		                 si sh_tgt ne peut créer directement le ..RTX
		             
		NB: ici seule utilisation de PREP_TO_SHELVES /?\
		"""
		gb_d = GCONF['grobid']['GROBID_HOME']
		gb_h = path.join(gb_d,'grobid-home')
		gb_p = path.join(gb_h,'grobid-home','config','grobid.properties')
		
		# todo faire mieux mais si possible rester indep de la version
		my_jar_path = glob(path.join(gb_d, 'grobid-core','target')
					  +"/grobid-core*.one-jar.jar")[0]
		
		# pdfs: unique input dir in any case
		pdf_dir_in = self.shelf_path('PDF0')
		
		
		# commun aux formes rawtxts et aux éventuels rawtoks
		exe_process = self.PREP_TO_SHELVES[tgt_model]['prep_exe']
		
		# temporary output_dir, elle aussi commune aux deux formes
		temp_dir_out = path.join(self.cdir, "temp_raws_%s" % tgt_model)
		
		if not path.exists(temp_dir_out):
			mkdir(temp_dir_out)
	
		grobid_prepare_args = ["java", "-jar",  my_jar_path,
									"-gH",   gb_h,
									"-gP",   gb_p,
									"-exe",  exe_process,
									"-dIn",  pdf_dir_in,
									"-dOut", temp_dir_out]
		
		print("**** PREPARATION MODELE %s ****" % tgt_model)
		print("ARGS:",grobid_prepare_args)
	
		# subprocess.call ++++++++++++++++++++++ appel système
		retval = call(grobid_prepare_args)
		
		# a posteriori
		for shelf in self.PREP_TO_SHELVES[tgt_model]['tgt_shelves']:
			shdir = self.shelf_path(shelf)
			shext = SHELF_STRUCT[shelf]['ext']
			
			if not path.exists(shdir):
				mkdir(shdir)
			
			# vérif et rangement
			for bn in self.bnames:
				just_created = path.join(temp_dir_out, bn+shext)
				tgt_in_shelf = path.join(shdir, bn+shext)
				if not path.exists(just_created):
					print("WARN: doc %s not done for model %s (skip)"
						   % (bn, tgt_model) )
				else:
					move(just_created, tgt_in_shelf)
		
		# ---------------------->8----------------------------------
		# hack pour les rawtxt non générables: bibfields authornames
		if 'sh_mktxt' in self.PREP_TO_SHELVES[tgt_model]:
			shfrom = self.PREP_TO_SHELVES[tgt_model]['sh_mktxt']['from']
			shto = self.PREP_TO_SHELVES[tgt_model]['sh_mktxt']['to']
			
			shfrom_ext = SHELF_STRUCT[shfrom]['ext']
			shto_ext = SHELF_STRUCT[shto]['ext']
			shtodir = self.shelf_path(shto)
			
			if not path.exists(shtodir):
				mkdir(shtodir)
			
			# lecture "from", transfo vers "to"
			for bn in self.bnames:
				new_shfrom = path.join(temp_dir_out, bn+shfrom_ext)
				tgt_in_shto = path.join(shtodir, bn+shto_ext)
				if not path.exists(new_shfrom):
					print("WARN: doc %s not done for model %s (skip)"
						   % (bn, tgt_model) )
				
				# sauvegarde >> .shto.rawtxt
				else:
					strip_tei_save_txt(new_shfrom, tgt_in_shto)
		# ---------------------->8----------------------------------
		
		# nettoyage
		rmtree(temp_dir_out)
		
		return retval
	# ------------------------------------------------------------------


def strip_tei_save_txt(tei_path_in, txt_path_out, start_tag="listBibl"):
	"""
	Helper function for rawtxt generation
	Opens, strips XML markup and saves.
	
	We start the rendering only at listBibl because this 
	function is only used in bibfields and authornames models
	(they wouldn't need what precedes)
	
	
	# dans notre contexte, c'est SEMI-SATISFAISANT
	 > prendre dans le training.tei c'est un listBibl incertain
	 > mais tout de même le gros des bibl est majoritairement là
	 > et c'est bien le listBibl tel que la cascade l'aurait eu
	"""
	tei_in = open(tei_path_in, 'r')
	all_lines = []
	on = False
	
	# first : diagnosis
	for line in tei_in.readlines():
			# trigger: a lone listBibl
			if match(r'^\s*<%s>$' % start_tag, line):
				on = True
			if match(r'^\s*</%s>$' % start_tag, line):
				on = False
			if on:
				# one or more sub-lines
				sublines = line.split('<lb/>')
				# (rather one but for the rare cases are interesting)
				for sline in sublines:
					# strip fixed indent
					sline = sub(r'^\t+', '', sline)
					
					# >> strip all xml tags <<
					sline = sub(r'<[^>]+>', '', sline)
					
					# convert 5 entities back to text
					sline = sub(r'&amp;', '&', sline)
					sline = sub(r'&lt;',  '<', sline)
					sline = sub(r'&gt;',  '>', sline)
					sline = sub(r'&quot;', '"', sline)
					sline = sub(r'&apos;', "'", sline)
					
					all_lines.append(sline)
	tei_in.close()
	txt_fh = open(txt_path_out, 'w')
	# lines still have their newlines
	txt_fh.write(''.join(all_lines))
	txt_fh.close()
