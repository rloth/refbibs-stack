#! /usr/bin/python3
"""
Common corpus management

changelog v0.3: No fixed "corpus_home" container
                (must be specified at init)
                No workshop_home either (this script_dir instead)
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.3"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from os              import path, mkdir, rename
from shutil          import rmtree, move
from re              import match, search, sub, escape, MULTILINE
from csv             import DictReader
from collections     import defaultdict
from subprocess      import call
from json            import dump, load

# Infos structurelles de corpus par défaut
BSHELVES = {
  # basic set ----------------------------------------------------------
  'PDF0': {'d':'A-pdfs',       'ext':'.pdf',      'api':'fulltext/pdf'},
  'XMLN': {'d':'B-xmlnatifs',  'ext':'.xml',      'api':'metadata/xml'},
  'GTEI': {'d':'C-goldxmltei', 'ext':'.tei.xml'},
  # --------------------------------------------------------------------
}

# pour trouver etc/dtdmashup et etc/pub2TEI installés avec ce fichier
THIS_SCRIPT_DIR = path.dirname(path.realpath(__file__))

class Corpus(object):
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
	
	# ------------------------------------------------------------
	#             C O R P U S    I N I T
	# ------------------------------------------------------------

	# £TODO absolument une dir extraite de s1 sous la forme read_dir
	def __init__(self, ko_name, new_infos=None, 
					read_dir=False, 
						verbose=False, new_home=None,
							shelves_struct=BSHELVES):
		"""
		2 INPUT modes
		  -IN: *new_infos* : a metadata table (eg sampler output)
		                  (no fulltexts yet, no workdir needed)
		
		  -IN: *read_dir* : path to an existing Corpus dir
		                  (with data/ and meta/ subdirs, etc.)
		
		In both modes: *new_home* is THE_CONTAINER DIR (private _home)
		               + *shtruct* is A_SHELVES_STRUCTURE (private _shtruct)
		                      => shtruct = BSHELVES (Corpus obj) 
		                      => shtruct = UPDATED_SHELVES (TrainingCorpus obj)
		                 + *type* option 
		                      => type = 'gold' (Corpus obj) 
		                      => type = 'train' (TrainingCorpus obj)
		                   + *verbose* option (for init)
		
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
		if not path.exists(new_home):
			# suggérer bako assistant_installation à l'utilisateur ?
			raise FileNotFoundError(new_home)
		
		# VAR 1: **home** our absolute container address ----------
		# (version absolue du chemin de base indiqué à l'initialisation)
		self._home = path.abspath(new_home)
		
		# VAR 2: **shtruct** our absolute container address ----------
		# (structure <=> map)
		
		# si lecture: reprise table persistante (comme pour triggers plus loin)
		if read_dir:
			map_path = path.join(self.cdir,'meta','shelves_map.json')
			# initialize struct from meta shelves_map.json
			# 'shelves_map.json' <=> structure for each possible shelf of this instance
			shmap = open(map_path,'r')
			self._shtruct = load(shmap)     # json.load
			shmap.close()
			
			if verbose and (self._shtruct.keys() != BSHELVES.keys()):
				# signalement si corpus étendu 
				# => dépasse de la structure basique
				# (sans doute objet fille de Corpus)
				print("READCORPUS: corpus étendu /!\\")
				xtra_shelves = [mapdsh for mapdsh in self._shtruct if mapdsh not in BSHELVES]
				print(" => %i étagères supplémentaires:\n  %s" % (
						len(xtra_shelves),
						','.join(xtra_shelves)
						)
					)
		
		# si init nouveau: la table a dû être fournie à l'initialisation
		else:
			self._shtruct = shelves_struct
			
			# statique sauf si init objet fille
			save_shelves_map()
		 
		
		# VAR 3: >> name << should be usable in a fs and without accents (for saxonb-xslt)
		if type(ko_name) == str and match(r'[_0-9A-Za-z-]+', ko_name):
			self.name = ko_name
		else:
			raise TypeError("new Corpus('%s') needs a name str matching /^[0-9A-Za-z_-]+$/ as 1st arg" % ko_name)
		
		# VAR 4: **cdir** new dir for this corpus and subdirs ----------
		if not read_dir:
			self.cdir = path.join(new_home, ko_name)
			mkdir(self.cdir)
			mkdir(path.join(self.cdir,"data"))    # pour les documents
			mkdir(path.join(self.cdir,"meta"))    # pour les tables etc.
		else:
			# remove any trailing slash
			read_dir = sub(r'/+$', '', read_dir)
			read_root, read_subdir = path.split(read_dir)
			if not len(read_root):
				read_root='.'
			
			# check correct corpora dir
			if not path.samefile(read_root, new_home):
				print("WARN: reading a corpus in dir '%s' instead of default '%s'"
				      % (read_root, new_home) )
			
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


		# VAR 5: >> shelfs <<   (index de flags pour "sous-dossiers par format")
		#                           shelfs refer to dirs of docs
		#                           of a given format
		self.shelfs = {}
		# 'shelf_triggers.json' <=> presence/absence flags for each shelf
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
				for shname in self._shtruct:
					if path.exists(self.shelf_path(shname)):
						self.shelfs[shname] = True
					else:
						self.shelfs[shname] = False
				# persistence of shelf presence/absence flags
				self.save_shelves_status()
		
		else:
			# initialize empty
			for shname in self._shtruct:
				self.shelfs[shname] = False
				# ex: {
				# 	'PDF0' : False,       # later: self.shelf[shname] to True
				# 	'NXML' : False,       # if and only if the fulltext files
				# 	'GTEI' : False,       # have already been placed in their
				# }                      # appropriate subdir


		# VARS 6 and 7: >> meta << and >> cols << lookup tables --------
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
			# VARS 8: >> bnames << basenames for persistance slots
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
				
				# £TODO ici tree.json DATE x PUB
			
			# VARS 9: >> size <<  (nombre de docs dans 1 étagère)
			self.size = len(self.bnames)
			
		else:
			self.meta = None
			self.cols = None
			self.bnames = None
			self.size = 0
		
		# VARS 10: >> ctype << (type de corpus)
		# (trace volontairement en dur à l'initialisation)
		# (à réécrire si et seulement si réinstancié en corpus étendu)
		self.ctype = corpus_type
		touch_type = open(path.join(self.cdir,"meta","corpus_type.txt"), 'w')
		print(self.ctype+'\n', file=touch_type)
		touch_type.close()
		
		# print triggers
		if verbose:
			print("\n.shelfs:")
			triggers_dirs = []
			for shelf, bol in self.shelfs.items():
				on_off = ' ON' if bol else 'off'
				ppdir = self._shtruct[shelf]['d']
			for td in sorted(triggers_dirs):
				print("  > %-3s  --- %s" % (td[1], td[0]))
		
		print("\n===( CORPUS SIZE: %i docs )===\n" % self.size)

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
		if my_shelf in self._shtruct:
			shsubdir = self._shtruct[my_shelf]['d']
			shpath = path.join(self.cdir, 'data', shsubdir)
			return shpath
		else:
			return None
	
	def filext(self, the_shelf):
		"""
		File extension for this shelf
		"""
		# file extension
		return self._shtruct[the_shelf]['ext']
	
	
	def origin(self, the_shelf):
		"""
		If exists, theoretical api route origin
		or processor command origin
		for this shelf's contents
		"""
		# api_route
		if 'api' in self._shtruct[the_shelf]:
			return self._shtruct[the_shelf]['api']
		elif 'cmd' in self._shtruct[the_shelf]:
			return self._shtruct[the_shelf]['cmd']
		else:
			return None
	
	def fileid(self, the_bname, the_shelf, 
				shext=None, shpath=None):
		"""
		Filesystem path of a given doc in a shelf
		(nb: doesn't check if doc is there)
		
		A utiliser en permanence
		"""
		# file extension
		if not shext:
			shext = self._shtruct[the_shelf]['ext']
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
		if my_shelf in self._shtruct:
			shext = self._shtruct[my_shelf]['ext']
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
	
	def assert_docs(self, shname):
		"""
		Just sets the shelf flag to true
		(we assume the files have been put there)
		(and the fileids are automatically known from bnames + shelf_struct)
		"""
		if shname in self._shtruct:
			self.shelfs[shname] = True
	
	def save_shelves_status(self):
		"""
		Persistence for asserted shelves
		"""
		trig_path = path.join(self.cdir,'meta','shelf_triggers.json')
		triggrs = open(trig_path,'w')
		dump(self.shelfs, triggrs)     # json.dump
		triggrs.close()
	
	def save_shelves_map(self):
		"""
		Persistence for possible shelves and their structural info.
		"""
		map_path = path.join(self.cdir,'meta','shelves_map.json')
		# write shtruct to meta/shelves_map.json
		shmap = open(map_path,'w')
		dump(self._shtruct, shmap)      # json.dump
		shmap.close()
			
	
	
	def got_shelves(self):
		"""
		The list of present fulltexts shelves.
		"""
		all_sorted = sorted(self._shtruct, key=lambda x:self._shtruct[x]['d'])
		got_shelves = [sh for sh in all_sorted if self.shelfs[sh]]
		return got_shelves
	
	
	# ------------------------------------------------------------
	#         C O R P U S   B A S E   C O N V E R T E R S
	# ------------------------------------------------------------
	# Most common corpus actions
	#
	# (manipulate docs and create new dirs with the result)
	
	# GOLD NATIVE XML
	def dtd_repair(self, dtd_prefix=None, our_home=None, debug_lvl=0):
		"""
		Linking des dtd vers nos dtd stockées dans /etc
		ou dans un éventuel autre dossier dtd_prefix
		"""
		if not dtd_prefix:
			dtd_prefix = path.abspath(path.join(THIS_SCRIPT_DIR,'etc','dtd_mashup'))
			if debug_lvl >= 1:
				print("DTD REPAIR: new dtd_prefix: '%s'" % dtd_prefix)
		
		# corpus home
		if not our_home:
			our_home = self._home
		
		# ssi dossier natif présent
		if self.shelfs['XMLN']:
			todofiles = self.fileids(my_shelf="XMLN")
			
			# temporary repaired_dir
			repaired_dir = path.join(self.cdir, 'data', 'with_dtd_repaired')
			mkdir(repaired_dir)
			
			for fi in todofiles:
				fh = open(fi, 'r')
				long_str = fh.read()
				fh.close()
				
				# splits a doctype declaration in 3 elements
				 # lhs + '"' + uri.dtd + '"' + rhs
				m = search(
				  r'(<!DOCTYPE[^>]+(?:PUBLIC|SYSTEM)[^>]*)"([^"]+\.dtd)"((?:\[[^\]]*\])?[^>]*>)',
					long_str, 
					MULTILINE
					)
				
				if m:
					# kept for later
					left_hand_side = m.groups()[0]
					right_hand_side = m.groups()[2]
					
					# we replace the middle group uri with our prefix + old dtd_basename
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
					outfile = open(repaired_dir+'/'+filename, 'w')
					outfile.write(new_str)
					outfile.close()
				else:
					if not search(r'wiley', long_str):
						# wiley often has no DTD declaration, just ns
						print('dtd_repair (skip) no match on %s' % fi)
					# save as is
					filename = path.basename(fi)
					outfile = open(repaired_dir+'/'+filename, 'w')
					outfile.write(long_str)
					outfile.close()
			
			# rename to std dir
			orig_dir = self.shelf_path("XMLN")
			if debug_lvl >= 2:
				print ("dtd_repair: replacing native XMLs in %s by temporary contents from %s" %(orig_dir, repaired_dir))
			rmtree(orig_dir)
			rename(repaired_dir, orig_dir)
	
	
	# GOLDTEI
	def pub2goldtei(self, pub2tei_dir=None, our_home=None, debug_lvl = 0):
		"""
		Appel d'une transformation XSLT 2.0 Pub2TEI
		
		actuellement via appel système à saxonb-xslt
		(renvoie 0 si tout est ok et 2 s'il n'y a eu ne serait-ce qu'une erreur)
		"""
		
		# dans 99% des cas c'est la même corpus_home
		# que celle à l'initialisation de l'objet
		if not our_home:
			our_home = self._home
		
		print("*** XSL: CONVERSION PUB2TEI (NATIF VERS GOLD) ***")
		if not pub2tei_dir:
			# chemin relatif au point de lancement
			p2t_path = path.join(THIS_SCRIPT_DIR, 'etc', 'Pub2TEI', 'Stylesheets','Publishers.xsl')
		else:
			p2t_path = path.join(pub2tei_dir,
								'Stylesheets','Publishers.xsl')
			if not path.exists(p2t_path):
				print("%s doit au moins contenir Stylesheets/Publishers.xsl" % pub2tei_dir)
				
		
		# si dossier d'entrée
		if self.shelfs['XMLN']:
			# src
			xml_dirpath = self.shelf_path("XMLN")
			#tgt
			gtei_dirpath = self.shelf_path("GTEI")
			
			if debug_lvl > 0:
				print("XSL src dir: %s" % xml_dirpath)
				print("XSL tgt dir: %s" % gtei_dirpath)
			
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
			
			if debug_lvl > 0:
				print("XSL:dbg: appel=%s" % call_args)
			
			try:
				# subprocess.call -----
				retval= call(call_args)
			except FileNotFoundError as fnfe:
				if search(r"saxonb-xslt", fnfe.strerror):
					print("XSL: les transformations pub2tei requièrent l'installation de saxonb-xslt (package libsaxonb-java)")
					return None
				else:
					raise
			
			# renommage en .tei.xml comme attendu par fileids()
			for fid in self.bnames:
				rename(path.join(gtei_dirpath, fid+'.xml'),
						path.join(gtei_dirpath, fid+'.tei.xml'))
			
			# on ne renvoie pas de valeur de retour, on signale juste le succès ou non
			if retval == 0:
				print("*** XSL: CONVERSIONS RÉUSSIES ***")
			else:
				print("*** XSL: echec (partiel?) des conversions ***" % len(self.bnames))
