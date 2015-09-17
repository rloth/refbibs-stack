#! /usr/bin/python3
"""
Client for bibliographical annotator grobid-service

# TODO checks sur len(content) ?
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2015 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.5"
__email__     = "romain.loth@inist.fr"
__status__    = "Integration"

# TODO search with proxy transmettre params de conf => gro
from sys             import argv, stderr
from os              import path, mkdir, remove
from argparse        import ArgumentParser, RawDescriptionHelpFormatter
from configparser    import ConfigParser
from tempfile        import NamedTemporaryFile
from re              import sub, search, compile, MULTILINE
from json            import loads, dumps

from urllib.parse    import quote
from urllib.request  import urlopen
from urllib.error    import HTTPError, URLError

# Pool pour le traitement multitache lui-même
from multiprocessing import Pool

# + Value et Lock et c_int pour le compteur global
from multiprocessing import Value, Lock
from ctypes          import c_int

from datetime        import datetime
from lxml            import etree    # pour lecture des infos de modèles

# for identification of empty returns
void_listBibl = compile(r"<listBibl>[\n\s]+</listBibl>", MULTILINE)

def my_parse_args():
	"""Preparation du hash des arguments ligne de commande pour main()"""
	
	parser = ArgumentParser(
		formatter_class=RawDescriptionHelpFormatter,
		description="""
An ISTEX client for grobid-service, the bibliographical annotator.
==================================================================
 1) sends a query to API
 2) gathers all hits (in pdf)
 3) sends them to grobid
 4) gets back the bibs for each file, as TEI XML""",
		usage="bib-get.py -q 'lucene query'",
		epilog="- © 2014-15 Inist-CNRS (ISTEX) romain.loth at inist.fr -"
		)
	
	parser.add_argument('-q',
		dest="query",
		metavar='"corpusName:nature AND publicationDate:[1970 TO *]"',
		help="normal input: a lucene query to pass to the api, for retrieval of all bibs of all hits",
		type=str,
		required=False,
		action='store')
	
	parser.add_argument('-l','--list_in',
		metavar='ID_list.txt',
		help="an alternative input: a list of IDs of the pdfs to be retrieved from api.istex.fr and processed",
		type=str,
		required=False,
		action='store')
	
	parser.add_argument('-m','--maxi',
		metavar='100',
		help="a maximum limit of processed docs (if the query returned more hits, the remainder will be ignored)",
		type=int,
		default=None ,
		action='store')
	
	parser.add_argument('-c','--config',
		dest="config_path",
		metavar='path/to/alternate_config.ini',
		help="option to specify an alternate config file (default path is: <script_dir>/bib-get.ini)",
		type=str,
		default=None ,
		action='store')
	
	parser.add_argument('-p','--printconfig',
		dest="just_print_conf",
		help="print configuration file and exit",
		default=False,
		required=False,
		action='store_true') # bool
	
	parser.add_argument('-g', '--group_output',
		help="group all single TEI output files into one TEICorpus file at end of run",
		default=False,
		required=False,
		action='store_true') # bool
	
	parser.add_argument('-y', '--yes',
		help="auto-answer yes to interactive confirmation prompt (just before main run)",
		default=False,
		required=False,
		action='store_true') # bool
	
	args = parser.parse_args(argv[1:])
	
	# coherence checks:
	#  we want a single input triggering option on, all the others off
	if (bool(args.query) 
	     + bool(args.list_in)
	         + bool(args.just_print_conf) != 1):
		print ("""ERROR
Please choose one single input option among:
   -q 'a lucene query'
   -l an_ID_list.txt
(or choose to print conf with -p or print help with -h)
""", 
		file=stderr)
		exit(1)
	
	return args


def get(my_url):
	"""Get remote url *that contains a json* and parse it"""
	try:
		remote_file = urlopen(my_url)
		
	except URLError as url_e:
		# signale 401 Unauthorized ou 404 etc
		print("api: HTTP ERR (%s) sur '%s'" % 
			(url_e.reason, my_url), file=stderr)
		# Plus d'infos: serveur, Content-Type, WWW-Authenticate..
		# print ("ERR.info(): \n %s" % url_e.info(), file=stderr)
		exit(1)
	try:
		response = remote_file.read()
	except httplib.IncompleteRead as ir_e:
		response = ir_e.partial
		print("WARN: IncompleteRead '%s' but 'partial' content has page" 
				% my_url, file=stderr)
	remote_file.close()
	result_str = response.decode('UTF-8')
	json_values = loads(result_str)
	return json_values




def api_search(q, limit=None):
	"""
	Get concatenated hits array from json results of a lucene query on ISTEX api.
	(Returns a path to temporary file containing all hits)
	
	Keyword arguments:
	   q       -- a lucene query
	              ex: "hawking AND corpusName:nature AND pubdate:[1970 TO *]"
	
	Global var:
	   CONF    -- dict of config sections/values as in './bib-get.ini'
	
	the config dict should contain at least the 2 following values:
	   CONF['istex-api']['host']    -- ex: "api.istex.fr"
	   CONF['istex-api']['route']   -- ex: "document"
	
	Output format is a parsed json with a total value and a hit list:
	{ 'hits': [ { 'id': '21B88F4EFBA46DC85E863709CA9824DEED7B7BFC',
				  'title': 'Recovering information borne by quanta that '
						   'crossed the black hole event horizon'},
				{ 'id': 'C095E6F0A43EBE3E98E2E6E17DD8775617636034',
				  'title': 'Holographic insights and puzzles'}],
	  'total': 2}
	"""
	
	# préparation requête
	url_encoded_lucene_query = quote(q)
	
	# construction de l'URL
	base_url = 'https:' + '//' + CONF['istex-api']['host']  + '/' + CONF['istex-api']['route'] + '/' + '?' + 'q=' + url_encoded_lucene_query + '&output=' + "fulltext"
	
	# requête initiale pour le décompte
	count_url = base_url + '&size=1'
	json_values = get(count_url)
	n_docs = int(json_values['total'])
	print('%s documents trouvés' % n_docs, file=stderr)
	
	# limitation éventuelle fournie par le switch --maxi
	if limit is not None:
		n_docs = limit
	
	# le document temporaire renvoyé contiendra la liste des résultats
	tempfile = NamedTemporaryFile(
	                         mode='w', 
	                         encoding="UTF-8",
	                         prefix='tmp_api_hits_',
	                         suffix='.jsonlist', 
	                         dir=None,
	                         delete=False   # /!\
	                       )
	
	# ensuite 2 cas de figure : 1 requête ou plusieurs
	if n_docs <= 5000:
		# requête simple
		my_url = base_url + '&size=%i' % n_docs
		json_values = get(my_url)
		for hit in json_values['hits']:
			tempfile.write(dumps(hit)+"\n")
	
	else:
		# requêtes paginées pour les tailles > 5000
		print("Récupération des IDS et métadonnées... ", file=stderr)
		local_counter = 0
		for k in range(0, n_docs, 5000):
			print("%i..." % k, file=stderr)
			my_url = base_url + '&size=5000' + "&from=%i" % k
			json_values = get(my_url)
			for hit in json_values['hits']:
				local_counter += 1
				# si on a une limite par ex 7500 et que k va jq'à 10000
				if local_counter > n_docs:
					break
				else:
					tempfile.write(dumps(hit)+"\n")
	
	# cache file now contains one json hit (id + fulltext infos) per line
	tempfile.close()
	
	return(tempfile.name)



def seconds_to_pstr(sec):
	"""
	seconds => human readable delay string
	
	NB: arrondis de + en + grands
	     plus d'une minute => à 10 secondes près
	     plus d'une heure  => à 2 min près
	     plus d'un jour    => à 20 min près
	
	Ex:
	25     => '25s'
	70     => '1m10s'
	72     => '1m10s'
	80     => '1m20s'
	350    => '5m50s'
	72500  => '20h08m'
	72600  => '20h10m'
	223859 => '62h00m'
	223860 => '62h20m'
	"""
	
	sec = int(sec)
	m, s = divmod(sec, 60)
	h, m = divmod(m, 60)
	
	# print(h, m, s)
	
	if sec < 60:
		return str(sec)+'s'
	elif sec >= 60 and sec < 3600:
		if s < 55:
			return "%im%02is" % (m, 10*round(s/10))
		# threshold case where local rounding influences upper unit (=> minutes + 1)
		else:
			return "%sm00s" % str(m+1)
	elif sec >= 3600 and sec < 86400:
		if m < 59:
			return "%ih%02im" % (h, 2*round(m/2))
		else:
			return "%sh00m" % str(h+1)
	else:
		if m < 50:
			return "%ih%02im" % (h, 20*round(m/20))
		else:
			return "%sh00m" % str(h+1)



def grobid_models_info():
	"""
	Returns human readable string about grobid's CRF models.
	
	Tries to connect to grobid service in admin mode and retrieve
	the name of each model (segmentation, names, citations, etc)
	along with any other interesting config values.
	
	These values will be joined with '/' and shown in the log 
	(and in the header of the teiCorpus if -g)
	"""
	
	properties_url = "http://%s:%s/modelsProperties" % (
	      CONF['grobid-service']['host'],
	      CONF['grobid-service']['port'],
	      )
	try:
		properties = urlopen(properties_url)
		xml_response = properties.read()
	except Exception as e:
		# print("Grobid's models info couldn't be retrieved (just used for logging)", file=stderr)
		return "NO SPECIFIC INFO ABOUT CRF MODELS"
	
	tree = etree.fromstring(xml_response)
	my_infos = []
	for prop in tree.xpath('/modelconfig/property'):
		value = sub("^[^_]+_", "", prop.find('value').text)
		value = sub("^seg", "bibzone", value)
		value = sub("^refseg", "biblines", value)
		value = sub("^cit", "bibfields", value)
		my_infos.append(value)
	
	model_names = sorted(my_infos, reverse=True)
	return model_names

def get_grobid_bibs_on_api_docs(istex_id):
	"""
	Calls grobid-service GET route /processReferencesViaUrl?pdf_url= allowing to process remote PDFs (eg from istex api)
	
	The pdfs urls always have the form:
	https://api.istex.fr/document/<HERE_ISTEX_ID>/fulltext/pdf
	
	Unique non-kw argument:
	   istex_id  -- ex:21B88F4EFBA46DC85E863709CA9824DEED7B7BFC
	
	Returns the TEI generated by grobid-service annotator
	"""
	
	# ID => PDF URL sur l'api
	the_pdf_url = "https://%s/%s/%s/fulltext/pdf" % (
	          CONF['istex-api']['host'], 
	          CONF['istex-api']['route'],
	          istex_id
	         )
	
	# route pour interroger grobid
	grobid_base = "http://%s:%s/%s" % (
	          CONF['grobid-service']['host'], 
	          CONF['grobid-service']['port'], 
	          CONF['grobid-service']['route']
	          )
	
	# requête à envoyer à grobid
	get_tei_url = "%s?pdf_url=%s" % (grobid_base, the_pdf_url)
	
	try:
		# interrogation ============================
		grobid_answer_content = urlopen(get_tei_url)
		# ==========================================
		
		# urlopen a renvoyé un objet file-like
		result = grobid_answer_content.read()
		grobid_answer_content.close()
		result_tei = result.decode('UTF-8')
		
		# --- post-traitements optionels sur chaque TEI ---------->8-----
		# on simplifie l'entête avant d'écrire le fichier
		if len(result_tei) and not search(void_listBibl, result_tei):
			result_tei = sub('<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xlink="http://www.w3.org/1999/xlink" \n xmlns:mml="http://www.w3.org/1998/Math/MathML">', 
			                    '<TEI xml:id="istex-%s">' % istex_id,
			                    result_tei)
			
			# on simplifie l'indentation
			result_tei = sub("\t", " ", result_tei)
		# tei vide de bibs
		else:
			# si 0 refbibs trouvées on ferme la balise TEI tout de suite
			result_tei = '<TEI xml:id="istex-%s"/>' % istex_id
		# -------------------------------------------------------->8-----
		
		# SORTIE > fichier tei individuel  ID.refbibs.tei.xml
		out_path = path.join(
							outdir,
							istex_id + CONF['output']['tei_ext']
						)
		out_file = open(out_path, 'w')
		out_file.write(result_tei)
		out_file.close()
		
	except HTTPError as e:
		print ("HTTP error %s on %s: skip" % (e.code, istex_id),
		        file=stderr)
	
	# ++ shared counter with lock
	increment()
	if counter.value%500 == 0:
		print("done: %i" % counter.value)


########################################################################
########################################################################
if __name__ == '__main__':
	
	# -- arguments ligne de commande -------------------------------
	args = my_parse_args()
	
	# -- lecture de fichier config ---------------------------------
	CONF = ConfigParser()
	
	# emplacement par défaut: ./bib-get.ini
	if args.config_path is None:
		script_dir = path.dirname(path.realpath(__file__))
		conf_path = path.join(script_dir, 'bib-get.ini')
	else:
		# emplacement spécifié par l'utilisateur
		conf_path = args.config_path
	
	conf_file = open(conf_path, 'r')
	conf_str = conf_file.read()
	conf_file.close()
	CONF.read_string(conf_str, source=conf_path)
	
	if args.just_print_conf:
		print(conf_str)
		exit(0)
	
	# -- vérification de l'existence de lieux de sortie ------------
	timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
	
	outdir = "%s-%s" % (timestamp, CONF['output']['dir'])
	if not path.isdir(outdir):
		print ("Création du dossier de sortie '%s'." % outdir, file=stderr)
		mkdir(outdir)
	
	outfile = None
	if args.group_output:
		outfile = "%s-%s" % (timestamp, CONF['output']['corpusfile'])
		print ("Fichier groupé de sortie: '%s'." % outdir, file=stderr)
	
	# -- vérification de la connectivité avec un service grobid ----
	gbcf = CONF['grobid-service']
	gburl = "http://%s:%s" % (gbcf['host'],gbcf['port'])
	
	try:
		gb_resp = urlopen(gburl)
		gb_resp.close()
	except URLError as url_e:
		print("Impossible de se connecter au service grobid. Veuillez vérifier qu'il tourne bien sur %s" % gburl)
		exit(1)
	
	print("Connection au service grobid sur #%s#" % gbcf['host'])
	
	# -- todo list: large ID + meta file ---------------------------
	# (RAM: ~ 1GB for 10 millions docs)
	ids_ok = []
	
	# -- init global counter ---------------------------------------
	counter = Value(c_int)  # defaults to 0
	# borrowed from stackoverflow.com/questions/1233222/
	counter_lock = Lock()
	def increment():
		with counter_lock:
			counter.value += 1
	
	# -- input list preparation ------------------------------------
	#  > Mode 1: an ES query gets us the input IDs
	if args.query:
		hit_file_path = api_search(q=args.query, limit=args.maxi)
		
		hit_file = open(hit_file_path)
		
		# on lit/vérifie les réponses et s'il y a du PDF on les garde
		n_got = 0
		ids_sans_pdf = []
		
		for line in hit_file:
			n_got += 1
			hit = loads(line)
			mon_id = hit['id']
			has_pdf = False
			# vérification s'il y a du PDF ?
			for file_meta in hit['fulltext']:
				if file_meta['extension'] == 'pdf':
					has_pdf = True
					break
			if has_pdf:
				ids_ok.append(mon_id)
			else:
				ids_sans_pdf.append(mon_id)
		
		print("%s récupérés\n  dont %s sans pdf" % 
			  (n_got,           len(ids_sans_pdf)), file=stderr)
		
		# fermeture et suppression définitive du fichier tempo
		hit_file.close()
		remove(hit_file_path)
	
	#  > Mode 2: the IDs are provided on external list
	#             (no checks)
	elif args.list_in:
		filehandle = open(args.list_in)
		ids_ok = [line.rstrip() for line in filehandle]
		filehandle.close()
	
	# -- runtime details -------------------------------------------
	
	# basic info
	n_docs       = len(ids_ok)
	model_names  = grobid_models_info()
	
	# estimated processing time = n_docs / (ncpu * avg_docs_per_sec_per_cpu)
	estim_ptime = n_docs/(int(CONF['process']['service-ncpu']) * 1.025)
	
	# output format details
	out_mode = None
	if args.group_output:
		out_mode = "1 grand fichier groupé \n                     > %s-output_bibs.teiCorpus.xml" % timestamp
	else:
		out_mode = "1 fichier par document \n                     > %s-output_bibs_dir/* " % timestamp
	
	print('--------------------------')
	print('    R U N    I N F O S')
	print('--------------------------')
	print('-> %s document%s à traiter' % (n_docs, "s" if n_docs !=1 else ""))
	print("-> modèles de balisage: \n    %s" % "\n    ".join(model_names))
	print("-> type de sortie:   %s" % out_mode)
	print('--------------------------')
	print("TEMPS DE TRAITEMENT APPROXIMATIF: %s" % seconds_to_pstr(estim_ptime))
	
	# ask user for approval before run
	if args.yes:
		utilisateur = "y"
	else:
		utilisateur = input("ok pour lancer le traitement ? (y/n) ")
	
	if utilisateur in ['y', 'Y', 'yes']:
		
		# dans tous les cas: traitement de la liste ids_ok
		
		# lancement ################################
		
		# NB : le lancement en parallèle sur ncpu processus
		#      est à dimensionner selon les processeurs alloués
		#      au grobid-service plutôt que ceux de la machine client !!!
		#
		#    Par exemple si j'ai ncpu = 5 sur le grobid-service et
		#    seulement 2 processeurs sur la machine client, je mets
		#    service-ncpu = 5 dans la config !!!
		
		# ===== get_grobid_bibs_on_api_docs()  =============
		process_pool = Pool(int(CONF['process']['service-ncpu']))
		process_pool.map(get_grobid_bibs_on_api_docs, ids_ok)
		process_pool.close()
		# ==================================================
	
	# toute autre réponse utilisateur que y, Y, yes
	else:
		print("Traitement annulé", file=stderr)
		exit()
	
	# a posteriori: optional concatenation of XMLs >> TEICorpus
	if args.group_output:
		
		model_infos = "models:" + "/".join(model_names)
		source_infos = None
		if args.list_in:
			source_infos = "%s documents obtenus par liste d'identifiants préparé (sous %s)" % (n_docs, args.list_in)
		else:
			source_infos = "%s documents obtenus par requête sur l'API ISTEX (q=%s)" % (n_docs, args.query)
		
		teico = open(outfile, "w")
		# un header pour tous
		global_header = """<?xml version="1.0" encoding="UTF-8" ?>
<teiCorpus xml:id="%s">
 <teiHeader type="corpus">
  <fileDesc>
   <titleStmt>
    <respStmt>
     <resp>Extraction Refbib</resp>
     <name>
       grobid.v.0.3.4 (via bib-get.py v.%s)
       %s
     </name>
    </respStmt>
    <extent>%s</extent>
   </titleStmt>
   <publicationStmt>
    <distributor>ISTEX</distributor>
   </publicationStmt>
  </fileDesc>
 </teiHeader>""" % ("refbibs-enrich-"+timestamp,
                    __version__,
                    model_infos, source_infos)
		print(global_header, file=teico)
		for idi in ids_ok:
			this_path = path.join(outdir, idi+CONF['output']['tei_ext'])
			try:
				this_tei = open(this_path, 'r')
			except FileNotFoundError as fnfe:
				# ECRITURE BALISE <TEI/> VIDE SI DOCUMENT ABSENT
				print(" <TEI xml:id=\"istex-%s\"/>" % idi, file=teico)
				continue
			# COPIE SI DOCUMENT PLEIN
			teico.write(this_tei.read())
			this_tei.close()
		
		# footer
		print("</teiCorpus>", file=teico)
		
		# voilà
		teico.close()
		
		print("OK:")
		print("  teiCorpus créé avec succès ----> %s" % outfile)
		print("  (le dossier %s peut dorénavant être supprimé)" % outdir)
		
		# il n'est pas nécessaire de garder le dossier des
		# tei individuels
