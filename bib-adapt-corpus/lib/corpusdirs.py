#! /usr/bin/python3
"""
Common corpus management
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.2"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from glob            import glob
from os              import mkdir, path
from shutil          import rmtree, move
from re              import match, search, sub, escape, MULTILINE
from csv             import DictReader
from collections     import defaultdict
from subprocess      import call, check_output, STDOUT
from configparser    import ConfigParser
from json            import dump, load

from site            import addsitedir     # pour imports locaux

# pour lib trainers.ragreage
addsitedir('lib/trainers')
import ragreage

# ----------------------------------------------------------------------
# read-in bib-adapt config values (workshop dirs, api conf, grobid home)
CONF = ConfigParser()

# default location: ../local_conf.ini (relative to this module)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, '..', 'local_conf.ini')
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()
# ----------------------------------------------------------------------
# Globals

# Infos structurelles de corpus, étendues ("shelf" pour "étagère")
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
			},
	'BZTEI': {'d':  'D.1.z-trainers-bibzone_tei',
			  'ext':'.training.segmentation.tei.xml',
			},
	
	# biblines = referenceSegmentation ---------------
	'BLRTX': {'d':  'D.2.a-trainers-biblines_rawtxt',
			  'ext':'.training.referenceSegmenter.rawtxt',
			},
	'BLRTK': {'d':  'D.2.b-trainers-biblines_rawtok',
			  'ext':'.training.referenceSegmenter',
			},
	'BLTEI': {'d':  'D.2.z-trainers-biblines_tei',
			  'ext':'.training.referenceSegmenter.tei.xml',
			},
	
	# bibfields = citations --------------------------
	'BFRTX': {'d':  'D.3.a-trainers-bibfields_rawtxt',
			  'ext':'.training.references.rawtxt',
			},
	'BFTEI': {'d':  'D.3.z-trainers-bibfields_tei', 
			  'ext':'.training.references.tei.xml',
			},
	
	# authornames = name/citation ---------------------
	'AURTX': {'d':  'D.4.a-trainers-authornames_rawtxt', 
			  'ext':'.training.citations.authors.rawtxt',
			},
	'AUTEI': {'d':  'D.4.z-trainers-authornames_tei', 
			  'ext':'.training.citations.authors.tei.xml',
			},
	}

PREP_TEI_FROM_TXT = {
					'bibzone' : {'from': 'BZRTX', 'to': 'BZTEI'},
					'biblines' : {'from': 'BLRTX', 'to': 'BLTEI'},
					'bibfields' : {'from': 'BFRTX', 'to': 'BFTEI'},
					'authornames' : {'from': 'AURTX', 'to': 'AUTEI'},
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
	home_dir = path.join(CONF['workshop']['HOME'],CONF['workshop']['CORPUS_HOME'])


	# ------------------------------------------------------------
	#             C O R P U S    I N I T
	# ------------------------------------------------------------

	# TODO absolument une dir extraite de s1 sous la forme read_dir
	def __init__(self, ko_name, new_infos=None, read_dir=False, verbose=False):
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
		
		if not path.exists(Corpus.home_dir):
			# suggérer bako assistant_installation à l'utilisateur ?
			raise FileNotFoundError(Corpus.home_dir)
		
		# VAR 1: >> name << should be usable in a fs and without accents (for saxonb-xslt)
		if type(ko_name) == str and match(r'[_0-9A-Za-z-]+', ko_name):
			self.name = ko_name
		else:
			raise TypeError("new Corpus('%s') needs a name str matching /^[0-9A-Za-z_-]+$/ as 1st arg" % ko_name)
		
		# VAR 2: **cdir** new dir for this corpus and subdirs ----------
		if not read_dir:
			self.cdir = path.join(Corpus.home_dir, ko_name)
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
			if not path.samefile(read_root, Corpus.home_dir):
				print("WARN: reading a corpus in dir '%s' instead of default '%s'"
				      % (read_root, Corpus.home_dir) )
			
			# check correct corpus dir name
			if read_subdir != ko_name:
				raise TypeError("""
ERROR -- Corpus(__init__ from dir): 
=> corpus name '%s' should be same as your dir %s <="""
				 % (ko_name, read_subdir) )
			else:
				self.cdir = read_dir
				
				# read corresponding infos
				infos_path = path.join(self.cdir,'meta','infos.tab')
				try:
					fi = open(infos_path,'r')    # todo idem pour triggers
				except FileNotFoundError as fnf_err:
					fnf_err.pi_mon_rel_path = path.join(ko_name, 'meta','infos.tab')
					raise fnf_err
				new_infos = fi.readlines()
				fi.close()
			
			if verbose:
				print(".rawinfos << %s" % infos_path)


		# VAR 7: >> shelfs <<   (index de flags pour "sous-dossiers par format")
		#                           shelfs refer to dirs of docs
		#                           of a given format
		self.shelfs = {}
		trig_path = path.join(self.cdir,'meta','shelf_triggers.json')
		
		if read_dir:
			# initialize shelfs from meta shelf_triggers.json
			try:
				triggrs = open(trig_path,'r')
				self.shelfs = load(triggrs)     # json.load
				triggrs.close()
			# or old way: initialize shelfs from subdir presence
			except:
				print("No saved shelf_triggers.json, regenerating from dirs")
				for shname in SHELF_STRUCT:
					if path.exists(self.shelf_path(shname)):
						self.shelfs[shname] = True
					else:
						self.shelfs[shname] = False
				# this time we save it
				self.save_shelves_status()
		
		else:
			# initialize empty
			for shname in SHELF_STRUCT:
				self.shelfs[shname] = False
				# ex: {
				# 	'PDF0' : False,       # later: self.shelf[shname] to True
				# 	'NXML' : False,       # if and only if the fulltext files
				# 	'GTEI' : False,       # have already been placed in their
				# }                      # appropriate subdir


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
			
			if verbose:
				print(".cols:")
				print("  ├──['pub_year'] --> %s" % self.cols['pub_year'][0:3] + '..')
				print("  ├──['title']    --> %s" % [s[0:10]+'..' for s in self.cols['title'][0:3]] + '..')
				print("  └──%s --> ..." % [cname for cname in self.cols if cname not in ['pub_year','title']])
			
			# ----- fileids
			# VARS 5: >> bnames << basenames for persistance slots
			my_ids = self.cols['istex_id']
			my_lot = self.cols['corpus']
			self.bnames = []
			for i,did in enumerate(my_ids):
				self.bnames.append(my_lot[i]+'-'+did)
				# ex: wil-0123456789ABCDEF0123456789ABCDEF01234567
			
			# all saved files pertaining to the same document object
			# will thus share the same basename, with a different .ext
			# usage: [id+lot =>] basenames [=> fileids == fspaths]
			
			if not read_dir:
				# SAVE META: infos to filesystem
				tab_fh = open(path.join(self.cdir,'meta','infos.tab'),'w')
				tab_fh.write("\n".join(new_infos) + "\n")
				tab_fh.close()
				# SAVE META: basenames
				bn_fh = open(path.join(self.cdir,'meta','basenames.ls'),'w')
				bn_fh.write("\n".join(self.bnames) + "\n")
				bn_fh.close()
				# SAVE META: shelfs (flags if some fulltexts already present)
				triggrs = open(trig_path,'w')
				dump(self.shelfs, triggrs)     # json.dump
				triggrs.close()
				
				# £TODO ici foreach col
				# £TODO ici tree.json DATE x PUB
			
		
		else:
			self.meta = None
			self.cols = None
			self.bnames = None
		
		# print triggers
		if verbose:
			print(".shelfs:")
			triggers_dirs = []
			for shelf, bol in self.shelfs.items():
				on_off = ' ON' if bol else 'off'
				ppdir = SHELF_STRUCT[shelf]['d']
				triggers_dirs.append([ppdir,on_off])
			for td in sorted(triggers_dirs):
				print("  > %-3s  --- %s" % (td[1], td[0]))
	

	# ------------------------------------------------------------
	#             C O R P U S    A C C E S S O R S
	# ------------------------------------------------------------
	
	# todo memoize
	def shelf_path(self, my_shelf):
		"""
		Returns the standard dir for a shelf: 
		   >> $cdir/data/$shsubdir <<
		(it contains the files of a given format)
		"""
		if my_shelf in SHELF_STRUCT:
			shsubdir = path.join(Corpus.home_dir, self.name, 'data', SHELF_STRUCT[my_shelf]['d'])
			shpath = path.join(self.cdir, 'data', shsubdir)
			return shpath
		else:
			return None
	
	def filext(self, the_bname, the_shelf, shext=None):
		"""
		basename + shelf extension
		£TODO : à mettre partout là où l'on a fait bname + shext à la main
		"""
		# file extension
		if not shext:
			shext = SHELF_STRUCT[the_shelf]['ext']
		
		# relative file id
		return the_bname+shext
	
	def fileid(self, the_bname, the_shelf, shext=None, shpath=None):
		"""
		Filesystem path of a given doc in a shelf
		(nb: doesn't check if doc is there)
		
		A utiliser en permanence
		"""
		# file extension
		if not shext:
			shext = SHELF_STRUCT[the_shelf]['ext']
		# standard shelf dir
		if not shpath:
			shpath = self.shelf_path(the_shelf)
		
		# real file path
		return path.join(shpath, the_bname+shext)

	def fileids(self, my_shelf):
		"""
		A list of theoretical files in a given shelf
		(filesystem paths)
		"""
		if my_shelf in SHELF_STRUCT:
			shext = SHELF_STRUCT[my_shelf]['ext']
			shpath = self.shelf_path(my_shelf)
			# faster than with simpler [_fileid(bn, my_shelf) for bn..]
			return [self.fileid(bn, my_shelf, shpath=shpath, shext=shext) 
										for bn in self.bnames]
		else:
			print("WARN: Unknown shelf type %s" % my_shelf)
			return None

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
	
	def save_shelves_status(self):
		"""
		Persistance for asserted shelves
		"""
		trig_path = path.join(self.cdir,'meta','shelf_triggers.json')
		triggrs = open(trig_path,'w')
		dump(self.shelfs, triggrs)     # json.dump
		triggrs.close()
	
	def fulltextsh(self):
		"""
		The list of present fulltexts shelves.
		"""
		
		all_sorted = sorted(SHELF_STRUCT, key=lambda x:SHELF_STRUCT[x]['d'])
		got_shelves = [sh for sh in all_sorted if self.shelfs[sh]]
		return got_shelves
	
	
	# ------------------------------------------------------------
	#         C O R P U S   B A S E   C O N V E R T E R S
	# ------------------------------------------------------------
	# Most common corpus actions
	#
	# (manupulate docs and create new dirs with the result)
	
	# GOLD NATIVE XML
	def dtd_repair(self, dtd_prefix=None):
		"""
		Linking des dtd vers nos dtd stockées dans /etc
		ou dans un éventuel autre dossier dtd_prefix
		"""
		if not dtd_prefix:
			work_home = CONF['workshop']['HOME']
			dtd_subdir = CONF['workshop']['CORPUS_DTDS']
			dtd_prefix = path.join(work_home,dtd_subdir)
			
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

	
	# GOLDTEI
	def pub2goldtei(self, p2t_lib=None):
		"""
		Appel d'une transformation XSLT 2.0 Pub2TEI
		
		actuellement via appel système à saxonb-xslt
		(renvoie 0 si tout est ok et 2 s'il n'y a eu ne serait-ce qu'une erreur)
		"""
		print("******** CONVERSION PUB2TEI VERS GOLD ********")
		if not p2t_lib:
			work_home = CONF['workshop']['HOME']
			p2t_lib = CONF['workshop']['PUB2TEI_XSL']
			p2t_path = path.join(work_home,p2t_lib,
			                     'Stylesheets','Publishers.xsl')
		
		# si dossier d'entrée
		if self.shelfs['XMLN']:
			xml_dirpath = self.shelf_path("XMLN")
			gtei_dirpath = self.shelf_path("GTEI")
			
			# mdkir dossier de sortie
			if not path.exists(gtei_dirpath):
				mkdir(gtei_dirpath)
			
			call_args = [
			"saxonb-xslt", 
			"-xsl:%s" % p2t_path,
			"-s:%s" % xml_dirpath,
			"-o:%s" % gtei_dirpath,
			# notre param pour les gold
			"teiBiblType=biblStruct",
			# éviter les simples quotes dans l'arg
			]
			
			# debug
			# print("XSLdbg: appel=%s" % call_args)
			
			# subprocess.call -----
			retval= call(call_args)
			
			# renommage en .tei.xml comme attendu par fileids()
			for fid in self.bnames:
				move(path.join(gtei_dirpath, fid+'.xml'),
				     path.join(gtei_dirpath, fid+'.tei.xml'))
			
		return retval

	# -----------------------------------------------------------------
	#    C O R P U S   P R E - T R A I N I N G   C O N V E R T E R S
	# -----------------------------------------------------------------
	
	# TRAINING RAWTXT instructions pour corpus.grobid_create_training()
	
	# PREP_TEI_FROM_TXT
	# grobid_create_training implique naturellement un traitement commun
	# mais les accès ensuite et l'usage des documents seront distincts..
 
	# /!\ les sh_tgt pour bibfields et authornames ne donnent pas de txt
	#	 on le créera depuis les tei de prépa => £TODO modif grobid
 
	# /!\ dans ts les cas on ne conserve pas les tei de prépa (non gold)
	#	 => n'apparaissent pas dans sh_tgt
	PREP_TEI_FROM_TXT = {
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
	
	
	# TRAINING RAWTXT central
	# todo skip if (wiley or nature) and (bibfields ou authornames)
	def grobid_create_training(self, tgt_model):
			"""
			Appel de grobid createTraining (pour les rawtoks et les rawtxts)
			
			Les instructions de traitement sont :
				 - la liste des modèles à faire pour grobid
				 - un dic PREP_TEI_FROM_TXT aux entrées de la forme:
			
			'nom_modele':{'prep_exe': commande grobid,
							 'tgt_shelves' : [étagères à récupérer],
							 },
			
			cf. aussi grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/
				sous "Generation of training data"
			
			hack : une clé supplémentaire 
					  'sh_mktxt': pointe une étagère permettant de refaire le texte
								si sh_tgt ne peut créer directement le ..RTX
							
			NB: ici seule utilisation de PREP_TEI_FROM_TXT /?\
			"""
			gb_d = CONF['grobid']['GROBID_HOME']
			gb_h = path.join(gb_d,'grobid-home')
			gb_p = path.join(gb_h,'grobid-home','config','grobid.properties')
			
			# todo faire mieux mais si possible rester indep de la version
			my_jar_path = glob(path.join(gb_d, 'grobid-core','target')
										 +"/grobid-core*.one-jar.jar")[0]
			
			# pdfs: unique input dir in any case
			pdf_dir_in =  path.join(self.cdir,self.shelf_path('PDF0'))
			
			
			# commun aux formes rawtxts et aux éventuels rawtoks
			exe_process = self.PREP_TEI_FROM_TXT[tgt_model]['prep_exe']
			
			# temporary output_dir, elle aussi commune aux deux formes
			temp_dir_out = path.join(self.cdir, "temp_raws_%s" % tgt_model)
			
			if not path.exists(temp_dir_out):
				mkdir(temp_dir_out)
				print("TMP: création dossier %s" % temp_dir_out)
			
			
			grobid_prepare_args = ["java", "-jar",  my_jar_path,
											"-gH",   gb_h,
											"-gP",   gb_p,
											"-exe",  exe_process,
											"-dIn",  pdf_dir_in,
											"-dOut", temp_dir_out]
			
			
			print("******** PREPARATION RAWTXTs pour %s ********" % tgt_model)
			print("Grobid running process '%s' \n -> on dir:%s, please wait..." % 
					(exe_process, pdf_dir_in))
			
			# subprocess.call ++++++++++++++++++++++ appel système
			gb_errs = check_output(grobid_prepare_args, stderr=STDOUT)
			
			print("GB:STDERR", gb_errs)
			
			print("%s ok... storing new docs in trainer dirs:" % tgt_model)
			
			# a posteriori
			for shelf in self.PREP_TEI_FROM_TXT[tgt_model]['tgt_shelves']:
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
					
					# on signale qu'on a réussi #£TODO test poussé
					self.assert_fulltexts(shelf)
					
					
			# ---------------------->8----------------------------------
			# hack pour les rawtxt non générables: bibfields authornames
			if 'sh_mktxt' in self.PREP_TEI_FROM_TXT[tgt_model]:
				shfrom = self.PREP_TEI_FROM_TXT[tgt_model]['sh_mktxt']['from']
				shto = self.PREP_TEI_FROM_TXT[tgt_model]['sh_mktxt']['to']
				
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
						if tgt_model == "bibfields":
							_strip_tei_save_txt(new_shfrom, tgt_in_shto, start_tag="listBibl")
						elif tgt_model == "authornames":
							_strip_tei_save_txt(new_shfrom, tgt_in_shto, start_tag="biblStruct")
		
				# on signale aussi qu'on a réussi
				self.assert_fulltexts(shto)
			# ---------------------->8----------------------------------
			
			# nettoyage
			rmtree(temp_dir_out)
			
			return None



	
	# TRAINING TEI ET RAGREAGE
	def construct_training_tei(self, tgt_model, just_rag = False, debug_lvl=0):
		"""
		Generic call to ragreage.py
		or 
		bibl[@type=trainerlike] specific XSLT
		
		Remarque: théoriquement on peut faire 2 procédures:
		
		Procédure just_rag => création des fulltexts depuis les PDF
	                      puis jonction (ragreage) avec les XML
	                      pour l'obtention des exemplaires annotés
	
		Procédure normale  => idem sauf pour Wiley et Nature qui ont
	                      déjà des bibl dans un markup acceptable
	                    (conversion en exemplaires directe, à part)
		"""
		
		print("******** PREPARATION specTEI pour %s ********" % tgt_model)
		
		src_txt_shelf = PREP_TEI_FROM_TXT[tgt_model]['from']
		tgt_tei_shelf = PREP_TEI_FROM_TXT[tgt_model]['to']
		
		print("SRC shelf", src_txt_shelf)
		
		# new folder
		new_dir = self.shelf_path(tgt_tei_shelf)
		if not path.exists(new_dir):
			mkdir(new_dir)
		
		# pour les tei d'entraînement on procède au cas par cas par fichiers
		# ------------------------------------------------------------------
		for i, bname in enumerate(self.bnames):
			lot = self.cols['corpus'][i]
			
			# modèles à traintei seule: selon lot
			if tgt_model in ['bibfields','authornames'] and not(just_rag) and lot in ['wil', 'nat']:
				# (todo) Le cas des feuilles wiley et nature : 
				# le ragreage n'est pas nécessaire si on veut
				# utiliser le flux natif, car le format est précis
				# TODO
				# possibilité: 
				# appel Pub2TEI  param teiBiblType fixé à 'bibl'
				# _tei_trainerlike_substitution(une_tei_lue, modele_visé)
				
				print("TODO cas trainerlike")
				#    c'est possible grace au produit des feuilles trainerlike
				#     => pour le modèle citations
				#         - supprimer tous les sauts de ligne interne
				#         - supprimer @rend='LB et LABEL'
				#         - supprimer @rend='DEL'
				#         - grouper @rend='GRP'
				#         - grouper les pages ET leur délimiteur non parsé
				#         - remplacer @unit par @type dans les biblScope
				#     => pour le modèle authornames
				#         - ne garder que chaque groupe auteur ou éditeur
				#         - garder les DEL
				#     
				#     NB pour le modèle refseg ce serait aussi envisageable
				#         - juste LABELS si présents, et tout le reste groupé 
				#           sauf rend=LB
				#         - mais actuellement pas alignable sur tokens...  
				pass
			
			# ici: modèles à rawtokens et/ou choix just_rag
			# => traitement purement par ragréage <=
			else:
				my_gold_tei_path = self.fileid(bname,'GTEI')
				my_raw_txt_path  = self.fileid(bname, src_txt_shelf)
				
				# générateur ("yield line" dans ragreage)
				line_gen = ragreage.run(
							# modèle
							the_model_type = tgt_model,
							# chemins
							the_txtin  = my_raw_txt_path,
							the_xmlin  = my_gold_tei_path,
							debug_lvl = debug_lvl
						   )
				
				my_train_tei_path = self.fileid(bname, tgt_tei_shelf)
				
				# écriture de chaque ligne ragrégée
				ttei_xml = open(my_train_tei_path, 'w')
				for tline in line_gen:
					ttei_xml.write(tline+"\n")
				ttei_xml.close()
			
			self.assert_fulltexts(tgt_tei_shelf)

		return None



# -----------------------------------------------------------------------------------
# TRAINING RAWTXT helper externe strip gb ptei
def _strip_tei_save_txt(tei_path_in, txt_path_out, start_tag="listBibl"):
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
	
	
	print("hello strip %s" % tei_path_in )
	
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
	txt_fh.write('\n'.join(all_lines)+'\n')   # todo vérifier les newlines
	txt_fh.close()
