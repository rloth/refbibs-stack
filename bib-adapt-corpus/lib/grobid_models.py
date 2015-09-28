#! /usr/bin/python3
"""
Simple CRF model fs management

TODO : 
  - model.backup_from_gb() => reprise depuis grobid courant, store sous nos models et lien là-bas 
  - model.restore_vanilla => dans grobid courant sous home/models + dans properties
  - model.push_to_gb() => dans grobid courant sous home/models + dans properties
  - mécanisme install_prod  => .push_to_gb
                            => git branch
                            => git commit & push

 Rappel :
 compilation rapide grobid
   mvn --offline -Dmaven.test.skip=true clean compile install
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.2"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from os              import makedirs, path, stat, listdir, symlink
from shutil          import copy, copytree
from re              import sub, search
from sys             import stderr
from configparser    import ConfigParser

# pour l'appel de grobid en training
from subprocess      import check_output, PIPE, Popen
from locale  import getlocale, setlocale, LC_TIME, LC_NUMERIC

# pour lire la version grobid
from lxml            import etree

# pour informer sur la date de création d'un modèle
from time            import localtime, strftime


# ----------------------------------------------------------------------
#                       [[ O U R    C O N F  ]]
# ----------------------------------------------------------------------
# read-in bib-adapt config values (model home dir, grobid home)

# NB la conf n'est essentielle *que* pour CRFModel.home_dir
#    (tout le reste pourrait être passé come arg)

CONF = ConfigParser()

# default location: ./global_conf.ini (relative to corpus.py)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, '..', 'local_conf.ini')
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()

# ----------------------------------------------------------------------
#                    [[ G R O B I D    I N F O S  ]]
# ----------------------------------------------------------------------
# as global constants #

# Valeurs stables de l'installation grobid 
#  | GB_DIR          (exemple: "/home/jeanpaul/grobid-integration-istex")
#  | GB_RAW_VERSION   (exemple: "0.3.4-SNAPSHOT")
#  | GB_VERSION       (exemple: "GB_0.3.4")
#  | GB_GIT_ID        (exemple: "4116965" ou "no_git")
# (pour rangement/suivi des modèles entraînés avec)

GB_DIR = CONF['grobid']['GROBID_DIR']

GB_RAW_VERSION = ""
try:
	gb_pom = [CONF['grobid']['GROBID_DIR'],'grobid-trainer','pom.xml']
	# print("CHEMIN POM de GB",path.join(*gb_pom))
	pom_xml = etree.parse(path.join(*gb_pom))
	version_elt = pom_xml.xpath('/*[local-name()="project"]/*[local-name()="version"]')[0]
	GB_RAW_VERSION = version_elt.text
	GB_VERSION = "GB_"+sub("-SNAPSHOT","",GB_RAW_VERSION)
except Exception as e:
	print("Problem while parsing %s: grobid version UNKNOWN, your grobid install is incomplete" % gb_pom)
	exit(1)

try:
	GB_GIT_ID = 'git_'+check_output(['git','--git-dir',GB_DIR+"/.git", 'log', '--pretty=format:%h', '-n1']).decode('UTF-8')
except Exception as e:
	GB_GIT_ID = 'no_git'

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

GB_CONF = ConfigParser()
gb_prop_path = path.join(GB_DIR,'grobid-home','config','grobid.properties')
gb_prop_file = open(gb_prop_path, 'r')
gb_conf_lines = ["[top]"] + [gb_property for gb_property in gb_prop_file]
GB_CONF.read_file(gb_conf_lines)
gb_prop_file.close()

def gb_model_dir(model_type = None):
	"""
	Expected dir of the active model.wapiti for model_type 
	(full path into the integration-grobid folders)
	"""
	base_path_elts = [CONF['grobid']['GROBID_DIR'],'grobid-home','models']
	tgt_path = None
	
	if model_type is None:
		raise ArgumentError("No model_type specified for gb_model_dir : bibzone, biblines, etc ?")
	else:
		# the full model path
		model_path_elts = GB_MODEL_MAP[model_type]['gbpath'].split('/')
		full_path_elts = base_path_elts + model_path_elts
		tgt_path = path.join(*full_path_elts)
	return tgt_path

def gb_model_import(model_type, to = None):
	if model_type is None:
		raise ArgumentError("No model_type specified for gb_model_import : bibzone, biblines, etc ?")
	elif to is None:
		raise ArgumentError("No target folder specified ? where are your models stored ?")
	else:
		# get mid !!!
		try:
			ID = GB_CONF['top']["models.%s" % GB_MODEL_MAP[model_type]['short']]
		except KeyError as ke:
			print("Out-of-the-box model had no name, calling it 'vanilla-%s'" % model_type)
			ID = "vanilla-%s" % model_type

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
			# on fait un lien qui permettra aux évaluations etc de restaurer le modèle
			symlink(path.join(new_dir,'model.wapiti'),
				path.join(gb_model_dir(model_type),'model.wapiti.vanilla'))



# ----------------------------------------------------------------------
#                    [[ M O D E L    S T O R E ]]
# ----------------------------------------------------------------------
class CRFModel:
	"""
	A wapiti CRF model with its location
	and standard operations/methods
	
	Usual slots:
	 -self.id
	 -self.mtype
	 -self.storing_path
	"""
	
	home_dir = path.join(CONF['workshop']['HOME'],CONF['workshop']['MODELS_HOME'])
	
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
		model_idno = max(actuels_nos)
	
	# ------------------------------------------------------------
	#             M O D E L    I N I T
	# ------------------------------------------------------------

	def __init__(self, the_model_type, existing_mid=None,
	             the_samples=[], debug_lvl = 0):
		"""
		en création:
		------------
		 IN: MODEL_TYPE + SAMPLE(S) + grobid infos
		    si samples = None => vanilla
		
		ou en import:
		   ----------
		 IN: MODEL_TYPE + model_id
		
		OUT: Model instance with:
			self.mid
			--------
			   =  <gb_name>[.<eps>]-<samp_id>
			
			self.samples
			------------
			   = corpora_names (list of strings)
			
			self.recipy
			------------
			   =  {train_params} # rempli lors du run
			
			self.mtype
			----------------
			   =  bibzone|biblines|bibfields|authornames
				 - traduction 1 => self.gb_mdltype_long()
				 - ? traduction 2 => self.gb_mdltype_short()
			
			self.storing_path
			-----------------
			   =  path.join(home_dir, 'run', model_id, 'model', 'model_type_long')
		"""
		
		if not path.exists(CRFModel.home_dir):
			# suggérer bako assistant_installation à l'utilisateur ?
			raise FileNotFoundError(CRFModel.home_dir)
		
		# VAR 1: id
		# exemple authornames-0.3.4-411696A-42
			
		# MODE CREATION #
		if existing_mid == None:
			self.model_idno += 1
			self.mid = "-".join([
				 the_model_type,
				 GB_VERSION,GB_GIT_ID,
				 '.'.join([name[0:4] for name in the_samples]),
				 str(self.model_idno)
				])
		# MODE IMPORT #
		else:
			# £todo check espaces et accents sur existing_mid
			self.mid = existing_mid
		
		# VAR 2: model_type
		self.mtype = the_model_type
		
		# VAR 3: storing_path
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		self.storing_path = path.join(CRFModel.home_dir, self.mid)
		
		# VAR 4: source samples names (list of strs)
		self.samples = the_samples
		
		# VAR 5: recipy
		self.recipy = None
		# £TODO remplir (lors du run?) avec gb_name, eps, win et self.samples
		
		# flags de statut
		self.ran = False
		self.picked = False
		self.evaluated = False
	
	
	
	# ------------------------------------------------------
	#         M O D E L    I N F O    M E T H O D S
	# ------------------------------------------------------
	def gb_mdltype_long(self):
		"""
		Returns the grobid long name of a model (str)
		exemple:
		  "segmentation"
		"""
		return GB_MODEL_MAP[self.mtype]['gbpath']
	
	
	
	# ------------------------------------------------------
	#         M A I N    M O D E L    T R A I N I N G
	# ------------------------------------------------------
	def call_grobid_trainer(self):
		"""
		ICI Appel training principal
		!!! Ne vérifie pas que les fichiers src sont au bon endroit !!!
		!!! Les TEI doivent être au moins non-vides !!!
		"""
		
		# exemple: "train_name_citation"
		model_cmd = GB_MODEL_MAP[self.mtype]['gbcmd']
		
		# on travaillera directement là-bas
		work_dir = path.join(CONF['grobid']['GROBID_DIR'],"grobid-trainer")
		
		# !!! locale = C !!!
		lc_numeric_backup = getlocale(LC_NUMERIC)
		setlocale(LC_NUMERIC, 'C')
		
		mon_process = Popen(
			  ['mvn',
			  # '--offline',
			  '-X',
			  'generate-resources',
			  '-P', model_cmd
			  ], 
			  stdout=PIPE, stderr=PIPE,
			  cwd=work_dir
		)
		
		self.ran = True
		
		crflog_lines = []
		
		for line in mon_process.stderr:
			print(line.decode('UTF-8').rstrip())
			crflog_lines.append(line.decode('UTF-8').rstrip())
		
		mvnlog_lines = [l.decode('UTF-8').rstrip() for l in mon_process.stdout]
		
		# on remet la locale comme avant
		setlocale(LC_NUMERIC, lc_numeric_backup)
		
		# => le modèle est à l'endroit habituel (cf. gb_model_dir())
		# => on ne renvoie donc que les logs         ----------------
		return (Logfile("training.mvn", mvnlog_lines),
				Logfile("training.crf", crflog_lines))
	
	
	
	# ------------------------------------------------------
	#         M O D E L   < = >   F I L E S Y S T E M
	# ------------------------------------------------------
	# filesystem interaction: import, pick_n_store, install
	
	
	def pick_n_store(self, logs=[], debug_lvl = 1):
		"""
		Recovers the new model from its standard grobid location and its logs
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
			print("Modèle trouvé:\n  %s\n  (%.1f MB) (created %s)" % (the_path, MB_size, ctime), file=stderr)
		
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
		
		# pour l'instant inutilisé ?
		self.picked = True
		
		# the stored location
		return new_model_dir
	
	
	# ------------------------------------------------------
	#            M O D E L    E V A L U A T I O N
	# ------------------------------------------------------
	#     actuellement tout est dans bako.eval_model()
	# ------------------------------------------------------




# ------------------------------------------------------------
#   [[ M I N I C L A S S    F O R    M O D E L    L O G S ]]
# ------------------------------------------------------------
class Logfile():
	"Simple et efficace"
	def __init__(self, logname, loglines):
		self.name = logname
		self.lines = loglines
	
	def print_to_file(self, fpath):
		lfile = open(fpath,'w')
		lfile.write('\n'.join(self.lines))
		lfile.close()