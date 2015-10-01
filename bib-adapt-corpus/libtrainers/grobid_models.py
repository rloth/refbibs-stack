#! /usr/bin/python3
"""
Simple CRF model fs management

TODO :
 - mécanisme install_prod
   via git:
    => .push_to_gb
    => git branch
    => git commit & push
   ou via rsync:
    => rsync GB_DIR/grobid-home/models/<GB_MODEL_MAP[mtype][gbpath]>/model.wapiti
             login@grobid-vp-machine:VP_GB_DIR/grobid-home/models/<GB_MODEL_MAP[mtype][gbpath]>/model.wapiti
                            
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.4"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from os              import makedirs, path, stat, listdir, symlink, remove
from shutil          import copy
from re              import sub, search, match
from configparser    import ConfigParser

# pour l'appel de grobid en training
from subprocess      import check_output, PIPE, Popen
from locale          import getlocale, setlocale, LC_NUMERIC

# pour lire la version grobid
from lxml            import etree

# pour informer sur la date de création d'un modèle
from time            import localtime, strftime

# pour nos fichiers de suivi 
from json            import dump, load
# (suivi global) MODELS_HOME/models_situation.json
# (suivi modèle) MODELS_HOME/model_name/recipy.json


# ----------------------------------------------------------------------
#                      [[  O U R    C O N F  ]]
# ----------------------------------------------------------------------
# read-in bib-adapt config values (model home dir, grobid home)

# NB la conf n'est essentielle *que* pour CRFModel.home_dir
#    (tout le reste pourrait être passé come arg)

BAKO_CONF = ConfigParser()

# default location: ./global_conf.ini (relative to corpus.py)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, '..', 'bako_config.ini')
conf_file = open(conf_path, 'r')
BAKO_CONF.read_file(conf_file)
conf_file.close()

MY_MODELS_HOME = path.join(
	BAKO_CONF['workshop']['HOME'],
	BAKO_CONF['workshop']['MODELS_HOME']
)

# ----------------------------------------------------------------------
#                   [[  G R O B I D    I N F O S  ]]
# ----------------------------------------------------------------------
# as global constants
# TODO mettre dans une fonction gb_get_infos()
#      lancée juste après un run_training
#      pour être sûr d'avoir des valeurs fraiches ?

# Valeurs stables de l'installation grobid ---------------------------
#  | GB_DIR          (exemple: "/home/jeanpaul/grobid-integration-istex")
#  | GB_RAW_VERSION  (exemple: "0.3.4-SNAPSHOT")
#  | GB_VERSION      (exemple: "GB_0.3.4")
#  | GB_GIT_ID       (exemple: "21713db" ou "no_git")
# (pour rangement/suivi des modèles entraînés avec)

GB_DIR = BAKO_CONF['grobid']['GROBID_DIR']

GB_RAW_VERSION = ""
try:
	gb_pom = [BAKO_CONF['grobid']['GROBID_DIR'],'grobid-trainer','pom.xml']
	# print("Lecture pom.xml de grobid sur chemin:",path.join(*gb_pom))
	pom_xml = etree.parse(path.join(*gb_pom))
	# noeud XML contenant par ex: "0.3.4-SNAPSHOT"
	version_elt = pom_xml.xpath(
		'/*[local-name()="project"]/*[local-name()="version"]'
		)[0]
	GB_RAW_VERSION = version_elt.text
	# ex: "GB_0.3.4"
	GB_VERSION = "GB_"+sub("-SNAPSHOT","",GB_RAW_VERSION)
	
except Exception as e:
	print("Problem while parsing %s: grobid version UNKNOWN, your grobid install is incomplete" % gb_pom)
	exit(1)

try:
	# ex: "21713db"
	GB_GIT_ID = 'git_'+check_output(
		['git','--git-dir',GB_DIR+"/.git",
		'log', '--pretty=format:%h', '-n1']
		).decode('UTF-8')
except Exception as e:
	GB_GIT_ID = 'no_git'

# --------------------------------------------------------------------
# associe les noms de dossiers (gbpath) 
# aux commandes grobid-trainer (gbcmd)
GB_MODEL_MAP = {
			'bibzone' : { 
				'gbpath': 'segmentation',
				'gbcmd' : 'train_segmentation',
				'short' : 'seg',
				},
			'biblines' : { 
				'gbpath': 'reference-segmenter',
				'gbcmd' : 'train_reference-segmentation',
				'short' : 'refseg',
				},
			'bibfields' : { 
				'gbpath': 'citation',
				'gbcmd' : 'train_citation',
				'short' : 'cit',
				},
			'authornames' : { 
				'gbpath': 'name/citation',
				'gbcmd' : 'train_name_citation',
				'short' : 'au',
				}
			}

# grobid.properties --------------------------------------------------
GB_PROP_PATH = path.join(GB_DIR,'grobid-home','config','grobid.properties')
GB_CONF = ConfigParser()
gb_prop_file = open(GB_PROP_PATH, 'r')
gb_conf_lines = ["[top]"] + [gb_property for gb_property in gb_prop_file]
GB_CONF.read_file(gb_conf_lines)
gb_prop_file.close()

# ----------------------------------------------------------------------
#  [[  G R O B I D - R E L A T E D    S T A T I C    H E L P E R S  ]]
# ----------------------------------------------------------------------

def gb_model_dir(model_type = None):
	"""
	Expected dir of the active model.wapiti file for model_type 
	(full path into the integration-grobid folders)
	"""
	base_path_elts = [BAKO_CONF['grobid']['GROBID_DIR'],'grobid-home','models']
	tgt_path = None
	
	if model_type is None:
		raise ArgumentError("No model_type specified for gb_model_dir : bibzone, biblines, etc ?")
	else:
		# the full model path
		model_path_elts = GB_MODEL_MAP[model_type]['gbpath'].split('/')
		full_path_elts = base_path_elts + model_path_elts
		tgt_path = path.join(*full_path_elts)
	return tgt_path


def gb_model_import(model_type, to = MY_MODELS_HOME):
	"""
	Imports an existing grobid model.wapiti file into a CRFModel class instance
	"""
	if model_type is None:
		raise ArgumentError("No model_type specified for gb_model_import : bibzone, biblines, etc ?")
	elif to is None:
		raise ArgumentError("No target folder specified ? where are your models stored ?")
	else:
		# get mid !!!
		try:
			ID = GB_CONF['top']["models.%s" % GB_MODEL_MAP[model_type]['short']]
		except KeyError as ke:
			print("Out-of-the-box model had no name, calling it '%s-vanilla'" % model_type)
			ID = "%s-vanilla" % model_type

		mon_modele = CRFModel(model_type, existing_mid = ID, the_samples = ['vanilla'])
		import_log = Logfile("vanilla.import",
							("importé par grobid_models.py %s" % __version__,
							 "mid='%s'" % ID))
		
		# ICI IMPORT ------( sauf si a déjà eu lieu )------
		skip_import = False
		try:
			new_dir = mon_modele.pick_n_store(logs=[import_log])
		except FileExistsError as fee:
			skip_import = True
			print("  skip_import: %s dir (unchecked) already exists in models dir" % ID)
		
		if not skip_import:
			# (persistance dans un json en amont pour tous les modèles)
			status_json = mon_modele.situation_read(models_home = to)
			# modif: c'est à la fois le modèle initial et le dernier en date
			status_json['vanilla'][model_type] = mon_modele.mid
			status_json['last'][model_type] = mon_modele.mid
			# écriture
			CRFModel.situation_write(status_json, models_home = to)
			
			# explication: ça note qu'on a fait un nouveau modèle vanilla pour
			#              pouvoir le restaurer (par ex. si évals un par un)
			
			# (persistance dans un json local pour les infos essentielles)
			mon_modele.recipy = {
				'model_id' : mon_modele.mid,
				'model_type' : mon_modele.mtype,
				'samples'   : ['INCONNUS'],
				'gb_infos' : {'gb_dir'     : GB_DIR,
				              'gb_version' : GB_VERSION,
				              'gb_git_id'  : GB_GIT_ID,
				              'import' : True}
				}
			mon_modele.save_recipy()
			# recipy =  petit fichier qui conservera les infos sur les jeux de modèles 
				#  - les modèles initiaux (vanilla_bibzone, vanilla_biblines, ...)
				#  - les modèles courants (last_bibzone, last_biblines, ...)
				#  - les meilleurs modèles (best_bibzone, best_biblines, ...)


def gb_vanilla_restore(model_type):
	"""
	Restores the pre-existing grobid model.wapiti from the store into grobid
	but as a symlink !
	"""
	if model_type is None:
		raise ArgumentError("No model_type specified for gb_model_import : bibzone, biblines, etc ?")
	elif model_type not in GB_MODEL_MAP:
		raise KeyError("Unknown model type %s" % model_type)
	else:
		# ok the model_type seems kosher!
		
		# a - read "situation report" to know vanilla ID
		status_info = CRFModel.situation_read()
		model_id_to_restore = status_info['vanilla'][model_type]
		
		# b - read vanilla object
		model_object = CRFModel(model_type, existing_mid=model_id_to_restore)
		
		# c - restore
		model_object.push_to_gb()
		
		# fyi the model we just reactivated
		return model_object.mid

# ----------------------------------------------------------------------
#                   [[  M O D E L    S T O R E  ]]
# ----------------------------------------------------------------------
class CRFModel:
	"""
	A wapiti CRF model with its location
	and standard operations/methods
	
	Usual slots:
	 -self._home
	 -self.id
	 -self.mtype
	 -self.storing_path
	"""
	
	# TODO: est-ce bien nécessaire ??
	home_dir = MY_MODELS_HOME
	
	# pour compter les instances => model ID
	
	# valeur par défaut
	model_idno = 0
	
	# s'il y a déjà des dossier modèles
	existing_mds = []
	if path.isdir(home_dir):
		existing_mds = listdir(home_dir)
	
	if existing_mds:
		# alors on prendra plutôt la plus grande des valeurs existantes
		actuels_nos = [int(sub(r".*-([0-9]+)$",r"\1",md)) for md in existing_mds if search(r".*-([0-9]+)$",md)]
		if len(actuels_nos):
			model_idno = max(actuels_nos)
		else:
			# il y a un ou plusieurs modèles non-numérotés
			# (hérités d'une version antérieure)
			model_idno = 1
	
	# ------------------------------------------------------------
	#             M O D E L    I N I T
	# ------------------------------------------------------------

	def __init__(self, the_model_type, the_samples=[],
	              existing_mid=None, existing_recipy=None,
	               debug_lvl = 0):
		"""
		en création:
		------------
		 IN: MODEL_TYPE + SAMPLE(S) + grobid infos
		    si samples = None => vanilla (= modèle baseline pré-existant)
		
		ou en import:
		   ----------
		 IN: MODEL_TYPE + model_id
		
		ou en lecture:
		   -----------
		 IN: MODEL_TYPE + model_id + existing_recipy_path
		
		
		OUT: Model instance with:
			self.mid
			--------
			   =  <gb_name>[.<eps>]-<samp_id>
			
			self.samples
			------------
			   = corpora_names (list of strings)
			
			self.gb_info
			------------
			   =  {grobid_params} # rempli lors du run
			
			self.recipy
			------------
			   =  {fields} # rempli lors du pick_n_store
			               # sauvegardé au même moment
			
			self.mtype
			----------------
			   =  bibzone|biblines|bibfields|authornames
				 - traduction 1 => self.gb_mdltype_long()
				 - ? traduction 2 => self.gb_mdltype_short()
			
			self._home
			-----------------
			   =  CRFModel.home_dir à l'initialisation
			
			self.storing_path
			-----------------
			   =  path.join(self._home, 'run', model_id, 'model', 'model_type_long')
		"""
		
		if not path.exists(CRFModel.home_dir):
			# suggérer bako assistant_installation à l'utilisateur ?
			raise FileNotFoundError(CRFModel.home_dir)
		
		# copie valeur telle qu'à l'initialisation
		self._home = path.abspath(CRFModel.home_dir)
		
		
		# £TODO permettre pas de model_type en mode lecture
		
		# MODE LECTURE : model_id et recipy.json #
		if existing_recipy:
			self.mid = existing_mid
			self.load_recipy()
			rmid = self.recipy['model_id']
			if rmid != self.mid:
				raise ValueError("ID mismatch recipy: %s <=> call: %s" %(rmid,self.mid))
			if self.recipy['model_type'] in GB_MODEL_MAP:
				self.mtype = self.recipy['model_type']
			else:
				raise TypeError("Unknown model_type '%s'" % self.recipy['model_type'])
			# /!\ pas de checks
			self.samples = self.recipy['samples']
			self.gb_infos = self.recipy['gb_infos']
		else:
			# MODE CREATION #
			# VAR 1: id
			# exemple authornames-0.3.4-411696A-42
			if existing_mid == None:
				self.model_idno += 1
				self.mid = "-".join([
					 the_model_type,
					 GB_VERSION,GB_GIT_ID,
					 '.'.join([name[0:4] for name in the_samples]),
					 str(self.model_idno)
					])
			# MODE IMPORT : model_id seul #
			else:
				# £todo check espaces et accents sur existing_mid
				self.mid = existing_mid
		
			# VAR 2: model_type
			self.mtype = the_model_type
			
			# VAR 3: storing_path
			# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
			self.storing_path = path.join(self._home, self.mid)
			
			# VAR 4: source samples names (list of strs)
			self.samples = the_samples
			
			# VAR 5: gb_infos
			# ne sera rempli que lors du run
			self.gb_infos = None
			
			# VAR 6: recipy
			# ne sera rempli que lors de pick_n_store
			self.recipy = None
			
			# VAR 7: score_ceterisparibus
			#        ("toutes_choses_egales_par_ailleurs")
			# ne sera rempli que lors de l'évaluation
			self.score_cp = None
		
		# flags de statut
		# remplacées par présence/absence des métas, respectivement:
		# initialisation <=> self.mtype, self.samples, self.storing_path
		# self.ran       <=> self.gb_infos
		# self.picked    <=> self.recipy + écriture des logs
		# self.evaluated <=> TODO self.score_cp
	
	# -----------------------------------------------------------
	#     C L A S S M E T H O D    M O D E L    R E A D E R
	# -----------------------------------------------------------
	@classmethod
	def take_from_store(cls, model_name, models_home=MY_MODELS_HOME):
		"""
		Reads model parameters from the model store
		and initializes a CRFModel object
		"""
		model_obj = cls(existing_mid = model_name)
	
	
	# -----------------------------------------------------------
	#   M E T H O D S    F O R    T H E    H O L E    C L A S S
	# -----------------------------------------------------------
	# these methods are relevant to all models taken together
	
	@staticmethod
	def situation_init():
		"""
		Creates a models-wide situation report with:
		  - initial models (vanilla imported from grobid)
		  - current models (installed in grobid)
		  # TODO - best models so far (in relation with bako.eval_models)
		
		the report is a dict object (to be saved as json)
		"""
		#  petit dict qui conservera les infos sur les jeux de modèles 
		#  - les modèles initiaux (vanilla_bibzone, vanilla_biblines, ...)
		#  - les modèles courants (last_bibzone, last_biblines, ...)
		#  - les meilleurs modèles (best_bibzone, best_biblines, ...)
		empty_report = {
		'vanilla' : {'bibzone':  None, 'biblines':   None,
		             'bibfields':None, 'authornames':None},
		 # ? possible: supprimer last ou remplacer par current
		'last' :    {'bibzone':  None, 'biblines':   None,
		             'bibfields':None, 'authornames':None},
		'best' :    {'bibzone':  None, 'biblines':   None,
		             'bibfields':None, 'authornames':None},
		}
		print("MODELS: new empty status report")
		return empty_report
	
	@classmethod
	def situation_read(cls, models_home=MY_MODELS_HOME):
		"""
		Reads the json all-models-wide situation report
		"""
		# (a) path de la sauvegarde
		bak_path = path.join(models_home,
							'models_situation.json')
		
		# si première fois
		if not path.exists(bak_path):
			print("MODELS: can't find any previous status report at %s" % bak_path)
			return cls.situation_init()
		else:
			# (b) lecture
			bak_read = open(bak_path,'r')
			models_situation_json = load(bak_read)
			bak_read.close()
			return models_situation_json

	@staticmethod
	def situation_write(models_situation_json, models_home=MY_MODELS_HOME):
		"""
		(Re-)writes the json situation report (usually after a change)
		"""
		bak_path = path.join(models_home,
							'models_situation.json')
		bak_write = open(bak_path,'w')
		# json.dump
		dump(models_situation_json, bak_write, indent=2)
		bak_write.close()


	# ------------------------------------------------------
	#         M O D E L    I N F O    M E T H O D S
	# ------------------------------------------------------
	def gb_mdltype_long(self, gb_model_map = GB_MODEL_MAP):
		"""
		Returns the grobid subdir of a model (str)
		exemple:
		  "segmentation"
		"""
		return gb_model_map[self.mtype]['gbpath']
	
	
	def gb_mdltype_short(self, gb_model_map = GB_MODEL_MAP):
		"""
		Returns the grobid shortname of a model (str)
		exemple:
		  "seg"
		"""
		return gb_model_map[self.mtype]['short']
	
	
	def gb_register_model_in_config(self, gb_prop_path = GB_PROP_PATH, debug_lvl=0):
		"""
		Rewrites grobid properties to register a newly installed model
		(as parameter:value INI pair)
		
		Exemple :
		models.seg=g034a.e-3_seg-grosto-478
		
		or:
		models.cit=bibfields-vanilla
		
		or:
		models.refseg=biblines-GB_0.3.4-git_4116965-bidu-479
		
		NB: ConfigParser can't do that because it requires subsections
			in the written output, which grobid doesn't want
			==> we do it by regexp
		"""
		
		# 'seg', 'refseg', 'cit' ou 'au'
		model_short_name = self.gb_mdltype_short()
		
		# ex: models.refseg=biblines-GB_0.3.4-git_4116965-bidu-479
		new_property_line = 'models.'+model_short_name+'='+self.mid+"\n"
		
		# exemple: '^models\.refseg *= *([^ ]+) *$'
		re_to_match = r'^models\.' + model_short_name + r' *= *([^ ]+) *$'
		
		# notre sortie
		modified_lines = []
		n_found = 0
		
		# lecture des propriétés actuelles
		gb_prop_file = open(gb_prop_path, 'r')
		for line in gb_prop_file:
			# on cherche mention pré-existante éventuelle
			found = match(re_to_match, line)
			
			if found:
				n_found += 1
				previous_model_name = found.groups()[0].rstrip()
				# replace
				changed_line = new_property_line
				print("MODELS: %s registered in grobid.properties" % self.mid)
				if debug_lvl > 1:
					print("  (by replacing previous:'%s')" % previous_model_name)
				modified_lines.append(changed_line)
			else:
				modified_lines.append(line)
		gb_prop_file.close()
		
		if n_found > 1:
			raise TypeError("MODELS: gb_register_model_in_config a trouvé %i mentions du même modèle => mise à jour du modèle compromise !!")
		elif n_found == 0:
			# on ajoute simplement une ligne à la fin
			# (il n'y avait rien de mentionné auparavant, 
			#   mais à présent ce sera le cas)
			modified_lines.append(new_property_line)
		
		# écriture
		gb_prop_file = open(gb_prop_path, 'w')
		gb_prop_file.write(''.join(modified_lines))
		gb_prop_file.close()

	
	# ------------------------------------------------------
	#         M A I N    M O D E L    T R A I N I N G
	# ------------------------------------------------------
	def call_grobid_trainer(self):
		"""
		ICI Appel training principal
		!!! Ne vérifie pas que les fichiers src sont au bon endroit !!!
		!!! Les TEI doivent être au moins non-vides et valides !!!
		"""
		
		# exemple: "train_name_citation"
		model_cmd = GB_MODEL_MAP[self.mtype]['gbcmd']
		
		# on travaillera directement là-bas
		work_dir = path.join(BAKO_CONF['grobid']['GROBID_DIR'],"grobid-trainer")
		
		# !!! locale = C !!!
		lc_numeric_backup = getlocale(LC_NUMERIC)
		setlocale(LC_NUMERIC, 'C')
		
		mon_process = Popen(
			  ['mvn',
			  # offline est intéressant *sauf la première fois*
			  # '--offline',
			  '-X',
			  'generate-resources',
			  '-P', model_cmd
			  ], 
			  stdout=PIPE, stderr=PIPE,
			  cwd=work_dir
		)
		
		crflog_lines = []
		
		for line in mon_process.stderr:
			print(line.decode('UTF-8').rstrip())
			crflog_lines.append(line.decode('UTF-8').rstrip())
		
		mvnlog_lines = [l.decode('UTF-8').rstrip() for l in mon_process.stdout]
		
		# on remet la locale comme avant
		setlocale(LC_NUMERIC, lc_numeric_backup)
		
		
		# self.ran = True
		# >> Le moment est venu de remplir self.infos <<
		# temporairement à partir des variables globales
		# £TODO mettre dans une fonction gb_get_infos()
		self.gb_infos = {
			'gb_dir'     : GB_DIR,
			'gb_version' : GB_VERSION,
			'gb_git_id'  : GB_GIT_ID
			}
		
		# enregistrement lié au niveau de grobid.propertires
		self.gb_register_model_in_config()
		
		# NB: l'enregistrement doit être lié à l'apparition d'un nouveau modèle
		#     même si dans les scénarios d'appel actuels on va toujours
		#     restaurer et ré-enregistrer vanilla juste après...
		
		
		# => le modèle est à l'endroit habituel (cf. gb_model_dir())
		# => on ne renvoie donc que les logs         ----------------
		return (Logfile("training.mvn", mvnlog_lines),
				Logfile("training.crf", crflog_lines))
	
	
	# ------------------------------------------------------
	#         M O D E L   < = >   F I L E S Y S T E M
	# ------------------------------------------------------
	# filesystem interaction: import, pick_n_store, push_to_gb
	
	
	def pick_n_store(self, logs=[], debug_lvl = 0):
		"""
		Recovers a new model from its standard grobid location and its logs
		+ stores it in the structured models home_dir with ID and creation info.
		"""
		# WHERE DO WE PICK FROM ?
		# the standard place for models created by grobid
		# ------------------------------------------------
		the_path = path.join(gb_model_dir(self.mtype), 'model.wapiti')
		
		if debug_lvl >= 1:
			# infos complémentaires : taille et date de création
			statinfo = stat(the_path)
			MB_size = statinfo.st_size/1048576
			ctime = strftime("%Y-%m-%d %H:%M:%S", localtime(statinfo.st_ctime))
			print("Modèle trouvé:\n  %s\n  (%.1f MB) (created %s)" % (the_path, MB_size, ctime))
		
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		new_base_dir = self.storing_path
		
		# dossier cible
		new_model_dir = path.join(
			new_base_dir,
			'model',
			# la même fin d'arborescence que
			# dans les dossiers originaux grobid
			GB_MODEL_MAP[self.mtype]['gbpath']
			)
		
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		makedirs(new_base_dir)
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42/model/name/citation
		makedirs(new_model_dir)
		
		copy(the_path, path.join(new_model_dir, 'model.wapiti'))
 
		# logs
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42/log
		new_log_dir = path.join(new_base_dir, 'log')
		makedirs(new_log_dir)
		
		# import log OR (mvn log + crf log)
		for log in logs:
			log.print_to_file(path.join(new_log_dir, '%s.log' % log.name))
			if debug_lvl >= 1:
				print("Wrote log %s" % log.name)
		
		
		# self.picked = True
		# >> Le moment est venu de remplir self.recipy <<
		
		# self.recipy est une meta qui sauvegarde: 
		#  - tout ce qu'il faut pour initialiser sauf storing_path
		#  - toutes infos complémentaires éventuelles
		self.recipy = {
			'model_id' : self.mid,
			'model_type' : self.mtype,
			'samples'   : self.samples,
			'gb_infos' : self.gb_infos
			}
		self.save_recipy()
		
		# the stored location
		return new_model_dir
	
	def push_to_gb(self, debug_lvl = 0):
		"""
		Installs a model from the model store into grobid
		   /!\\ overwriting the previous /!\\
		   /!\\      active model        /!\\
		
		Registers the model as current in:
		   - workshop_home/models/models_situation.json
		   - grobid-home/config/grobid.properties
		
		NB: if the previous active model was grobid's vanilla one,
		    it has normally been imported in the workshop under
		    vanilla-<modeltype>
		  
		   otherwise if it's a model we created then it is in 
		   the workshop models too
		  
		  in case of major mess-up, it should be still possible
		  to restore the original models from the git or tar
		  source of the grobid version used
		
		(reverse of pick_n_store)
		"""
		
		# target
		# -------
		tgt_dir = gb_model_dir(self.mtype)
		if not path.isdir(tgt_dir):
			print("MODELS.push_to_gb: Erreur: la destination paramétrée est absente et/ou n'est pas un dossier grobid-home/models normal ('%s'" % tgt_dir)
			pass
		else:
			tgt_path = path.join(tgt_dir, 'model.wapiti')
		
		# source
		# -------
		src_path = path.join(
			self.storing_path,
			'model',
			# toujours la même fin d'arborescence
			GB_MODEL_MAP[self.mtype]['gbpath'],
			'model.wapiti'
			)
		
		if not path.exists(src_path):
			raise FileNotFoundError
		else:
			# /!\ symlink en écrasant /!\
			if debug_lvl > 0:
				print("MODELS.push_to_gb: SYMLINK OVERWRITING %s" % tgt_path )
			remove(tgt_path)
			symlink(src_path, tgt_path)
			
			if debug_lvl > 0:
				print("MODELS.push_to_gb: enregistrement de la substitution au niveau du conteneur home")
			json_status = CRFModel.situation_read(models_home = self._home)
			json_status['last'][self.mtype] = self.mid
			CRFModel.situation_write(json_status, models_home = self._home)
			
			if debug_lvl > 0:
				print("MODELS.push_to_gb: enregistrement aussi au niveau de grobid")
			self.gb_register_model_in_config(debug_lvl=debug_lvl)
		
		
	# ------------------------------------------------------
	#            M O D E L    E V A L U A T I O N
	# ------------------------------------------------------
	#     actuellement tout est dans bako.eval_model()
	# ------------------------------------------------------
	
	
	# ------------------------------------------------------
	#           M E T A D A T A    P I C K L E
	# ------------------------------------------------------
	def save_recipy(self):
		"""
		Persistence for recipy (write all the object init/run details)
		"""
		recipy_path = path.join(self.storing_path,'recipy.json')
		recipy_file = open(recipy_path,'w')
		dump(self.recipy, recipy_file, indent=2)     # json.dump
		recipy_file.close()
	
	def load_recipy(self):
		"""
		Persistence for recipy (used to read back the object)
		"""
		recipy_path = path.join(self.storing_path,'recipy.json')
		recipy_file = open(recipy_path,'r')
		# /!\ no checks /!\ £TODO
		self.recipy = load(self.recipy, recipy_file)     # json.load
		recipy_file.close()



# ------------------------------------------------------------
#   [[ M I N I C L A S S    F O R    M O D E L    L O G S ]]
# ------------------------------------------------------------
class Logfile():
	"Simple et efficace"
	def __init__(self, logname, loglines):
		self.name = logname
		self.lines = loglines
	
	def print_to_file(self, fpath):
		"Le path est à fabriquer soi-même (à partir de self.name)"
		lfile = open(fpath,'w')
		lfile.write('\n'.join(self.lines))
		lfile.close()