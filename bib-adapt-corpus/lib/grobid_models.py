#! /usr/bin/python3
"""
Simple CRF model fs management

 Rappel :
 
 compilation rapide grobid
   mvn --offline -Dmaven.test.skip=true clean compile install
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from os              import makedirs, path, stat, listdir
from shutil          import copy, copytree
from re              import sub
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
# ----------------------------------------------------------------------
# Global constants
# ----------------

# G R O B I D    I N F O S
# Valeurs stables de l'installation grobid 
#  | GB_HOME    (exemple: "/home/jeanpaul/grobid")
#  | GB_VERSION (exemple: "GB_0.3.4")
#  | GB_GIT_ID  (exemple: "4116965")
# (pour rangement/suivi des modèles entraînés avec)

GB_HOME = CONF['grobid']['GROBID_HOME']

try:
	gb_pom = [CONF['grobid']['GROBID_HOME'],'grobid-trainer','pom.xml']
	# print("CHEMIN POM de GB",path.join(*gb_pom))
	pom_xml = etree.parse(path.join(*gb_pom))
	version_elt = pom_xml.xpath('/*[local-name()="project"]/*[local-name()="version"]')[0]
	version_elt.text = sub("-SNAPSHOT","",version_elt.text)
	GB_VERSION = "GB_"+version_elt.text
except Exception as e:
	print("Problem while parsing %s: grobid version UNKNOWN" % gb_pom)
	GB_VERSION = 'GB_UNKNOWN'

try:
	GB_GIT_ID = 'git_'+check_output(['git','--git-dir',GB_HOME+"/.git", 'log', '--pretty=format:%h', '-n1']).decode('UTF-8')
except Exception as e:
	print("Problem while looking for grobid git commit id in %s: UNKNOWN" % GB_HOME)
	GB_GIT_ID = 'git_unknown'



# S T R U C T U R E    D E    R A N G E M E N T 
# (à la coltrane)
#~ TIDY_STRUCT = {
	#~ # échantillon de travail
	#~ 'SAMP': {
		#~ '_id' : "<mdltype>-<name>-<nfiles>",
		#~ 'data': "<mdltype_long>",
		#~ 'meta': "<_id.readme>"
		#~ },
	#~ 
	#~ # resultat d'un run d'entraînement
	#~ 'MODL': {
		#~ '_id'  : "<gb_name>[.<eps>]-<samp_id>",
		#~ 'log'  : ["<_id>.crf.log", "<_id>.mvn.log"],
		#~ 'model': {"<mdltype_long>":'model.wapiti'}
		#~ },
	#~ 
	#~ # résultat d'une évaluation
	#~ 'EVAL': {
		#~ '_id' : "<corpus_shortname>-<gb_name>_<samp_id>+",
		#~ 'version.log':None,
		#~ 'gb_eval_<_id>.log':None,
		#~ 'gb_eval_<_id>.tab':None,
		#~ 'gb_eval_<_id>.shb':None,
		#~ 'TEI-back_done': "%res_tei%"
		#~ },
	#~ }

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# our Model class
# ----------------
class CRFModel:
	"""
	A wapiti CRF model with its locatation
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
	existing_mds = listdir(home_dir)
	
	if existing_mds:
		# alors on prendra plutôt la plus grande des valeurs existantes
		actuels_nos = [int(sub(r".*-([0-9]+)$",r"\1",md)) for md in existing_mds]
		model_idno = max(actuels_nos)
	
	model_map = {
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
	
	# ------------------------------------------------------------
	#             M O D E L    I N I T
	# ------------------------------------------------------------

	def __init__(self, the_model_type, the_samples=['vanilla'], debug_lvl = 0):
		"""
		IN: MODEL_TYPE + SAMPLE(S) + grobid infos
		    si samples = None => vanilla
		
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
			user_reply = input(
"""
PAUSE: Vos paramètres de config ont le dossier '%s'
comme lieu de stockage de tous les modèles CRF ("CRF Store")... mais il n'existe pas encore (nécessaire pour continuer)).

  => Voulez-vous le créer maintenant ? (y/n) """ % CRFModel.home_dir)
			
			if user_reply[0] in ['Y','y','O','o']:
				makedirs(CRFModel.home_dir)
			else:
				exit(1)
		
		# VAR 1: id
		# solution incrément TEMPORAIRE => TODO mieux
		self.model_idno += 1
		# exemple authornames-0.3.4-411696A-42
		self.mid = "-".join([
			 the_model_type,
			 GB_VERSION,GB_GIT_ID,
			 '.'.join([name[0:4] for name in the_samples]),
			 str(self.model_idno)
			])
		
		# VAR 2: model_type
		self.mtype = the_model_type
		
		# VAR 3: storing_path
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		self.storing_path = path.join(CRFModel.home_dir, self.mid)
		
		# VAR 4: source samples names (list of strs)
		self.samples = the_samples
		
		# VAR 5: recipy
		self.recipy = None
		# TODO remplir (lors du run?) avec gb_name, eps, win et self.samples
		
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
		return CRFModel.model_map[self.mtype]['gbpath']
	
	
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
		model_cmd = CRFModel.model_map[self.mtype]['gbcmd']
		
		# on travaillera directement là-bas
		work_dir = path.join(CONF['grobid']['GROBID_HOME'],"grobid-trainer")
		
		# !!! locale = C !!!
		lc_numeric_backup = getlocale(LC_NUMERIC)
		setlocale(LC_NUMERIC, 'C')
		
		mon_process = Popen(
			  ['mvn',
			  '--offline',
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
		
		return (mvnlog_lines, crflog_lines)
	
	# ------------------------------------------------------
	#         M O D E L   < = >   F I L E S Y S T E M
	# ------------------------------------------------------
	# filesystem interaction: pick, store, install_to_prod
	
	def pick_n_store(self, mvn_log_lines, crf_log_lines, debug_lvl = 1):
		"""
		Recovers the new model from its standard grobid location and its logs
		+ stores it in the structured models home_dir with ID and creation info.
		"""
		# WHERE DO WE PICK FROM ?
		# the standard place for models created by grobid
		# ------------------------------------------------
		base_path_elts = [CONF['grobid']['GROBID_HOME'],'grobid-home','models']
		model_path_elts = CRFModel.model_map[self.mtype]['gbpath'].split('/')
		
		full_path_elts = base_path_elts + model_path_elts + ['model.wapiti']
		the_path = path.join(*full_path_elts)
		
		if debug_lvl >= 1:
			# infos complémentaires : taille et date de création
			statinfo = stat(the_path)
			MB_size = statinfo.st_size/1048576
			ctime = strftime("%Y-%m-%d %H:%M:%S", localtime(statinfo.st_ctime))
			print("PICK MODEL:\n  %s\n  (%.1f MB) (created %s)" % (the_path, MB_size, ctime), file=stderr)
		
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		new_base_dir = self.storing_path
		
		model_dir_elts = [new_base_dir, 'model'] + model_path_elts
		new_model_dir = path.join(*model_dir_elts)
		
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		makedirs(new_base_dir)
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42/model/name/citation
		makedirs(new_model_dir)
		
		copy(the_path, path.join(new_model_dir, 'model.wapiti'))
 
		# logs
		# ex: /home/jeanpaul/models/authornames-0.3.4-411696A-42/log
		new_log_dir = path.join(new_base_dir, 'log')
		makedirs(new_log_dir)
		mvn_lfile = open(path.join(new_log_dir, 'training.mvn.log'),'w')
		mvn_lfile.write('\n'.join(mvn_log_lines))
		mvn_lfile.close()
		crf_lfile = open(path.join(new_log_dir, 'training.crf.log'),'w')
		crf_lfile.write('\n'.join(crf_log_lines))
		crf_lfile.close()
		
		self.picked = True
		
		# the stored location
		return new_model_dir


	# ------------------------------------------------------
	#            M O D E L    E V A L U A T I O N
	# ------------------------------------------------------