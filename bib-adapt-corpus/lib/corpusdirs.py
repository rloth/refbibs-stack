#! /usr/bin/python3
"""
Common corpus management
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.3"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# TODOSPLIT home_dir pas depuis CONF

from os              import path
from shutil          import move
from re              import match, search, sub, escape, MULTILINE
from csv             import DictReader
from collections     import defaultdict
from subprocess      import call
from json            import dump, load

# Infos structurelles de corpus basiques
SHELF_STRUCT = {
	# basic set --------------------------------------
	'PDF0' : {'d':'A-pdfs',       'ext':'.pdf'},
	'XMLN' : {'d':'B-xmlnatifs',  'ext':'.xml'},
	'GTEI' : {'d':'C-goldxmltei', 'ext':'.tei.xml'},
	# ------------------------------------------------
	}

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
	# TODOSPLIT remove
	#~ home_dir = path.join(CONF['workshop']['HOME'],CONF['workshop']['CORPUS_HOME'])
	home_dir = "neo_corpora_test_TODOSPLIT"


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
			
			# rename to std dir
			orig_dir = self.shelf_path("XMLN")
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
