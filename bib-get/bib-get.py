#! /usr/bin/python3
"""
Client for bibliographical annotator grobid-service

# TODO checks sur len(content) ?
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2015 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.2"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# TODO search with proxy transmettre params de conf => gro
from sys             import argv, stderr
from os              import path, makedirs, remove
from argparse        import ArgumentParser, RawDescriptionHelpFormatter
from configparser    import ConfigParser
from tempfile        import NamedTemporaryFile
from re              import sub, search, compile, MULTILINE
from json            import loads, dumps

from urllib.parse    import quote
from urllib.request  import urlopen
from urllib.error    import HTTPError, URLError

from multiprocessing import Pool

from datetime        import datetime
from lxml            import etree    # pour lecture des configs models


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
		metavar='"hawking AND corpusName:nature AND pubdate:[1970 TO *]"',
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
	
	parser.add_argument('-g', '--group_output',
		help="group all single TEI output files into one TEICorpus file at end of run",
		default=False,
		required=False,
		action='store_true')
	
	parser.add_argument('-y', '--yes',
		help="auto-answer yes to interactive confirmation prompt (just before main run)",
		default=False,
		required=False,
		action='store_true')
	
	args = parser.parse_args(argv[1:])
	
	# coherence checks:
	#  we want a single input option
	if (bool(args.query) + bool(args.list_in) != 1):
		print ("Please provide a single input option : -q 'a lucene query' OR -l an_ID_list.txt", file=stderr)
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
	print('%s documents found' % n_docs, file=stderr)
	
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
		print("Collecting result hits... ", file=stderr)
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
		model_name = sub("^models\.", "", prop.find('key').text)
		my_infos.append(model_name+'='+prop.find('value').text)
	
	info_string = "CRFs: " + " / ".join(my_infos)
	return info_string

def get_grobid_bibs(istex_id):
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
		
		
		
		
		# --- traitements optionels posteriori sur chaque TEI ---->8----
		# on simplifie l'entête
		if len(result_tei) and not search(void_listBibl, result_tei):
			result_tei = sub('<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xlink="http://www.w3.org/1999/xlink" \n xmlns:mml="http://www.w3.org/1998/Math/MathML">', 
			                    '<TEI xml:id="istex-%s">' % istex_id,
			                    result_tei)
			
			# on simplifie l'indentation
			result_tei = sub("\t", " ", result_tei)
		# tei vide de bibs
		else:
			result_tei = '<TEI xml:id="istex-%s"/>' % istex_id
		# -------------------------------------------------------->8----
		
		# SORTIE > fichier tei individuel  ID.refbibs.tei.xml
		out_path = path.join(
							CONF['output']['dir'],
							istex_id + CONF['output']['tei_ext']
						)
		out_file = open(out_path, 'w')
		out_file.write(result_tei)
		out_file.close()
		
	except HTTPError as e:
		print ("HTTP error %s on %s: skip" % (e.code, istex_id),
		        file=stderr)
	


########################################################################
########################################################################
if __name__ == '__main__':
	
	# arguments ligne de commande
	args = my_parse_args()
	
	# lecture de fichier config
	CONF = ConfigParser()
	
	# emplacement par défaut: ./bib-get.ini
	if args.config_path is None:
		script_dir = path.dirname(path.realpath(__file__))
		conf_path = path.join(script_dir, 'bib-get.ini')
	else:
		# emplacement spécifié par l'utilisateur
		conf_path = args.config_path
	
	conf_file = open(conf_path, 'r')
	CONF.read_file(conf_file)
	conf_file.close()
	
	# plus simple :
	# CONF = ConfigParser()
	# conf_file = open('bib-get.ini', 'r')
	# CONF.read_file(conf_file)
	# conf_file.close()
	
	# vérification de l'existence du dossier de sortie
	if not path.isdir(CONF['output']['dir']):
		print ("Please create the output dir '%s'." % CONF['output']['dir'], file=stderr)
		exit(1)
	
	# vérification de la connectivité avec un service grobid
	gbcf = CONF['grobid-service']
	gburl = "http://%s:%s/%s" % (gbcf['host'],gbcf['port'])
	
	try:
		urlopen(gburl)
	except URLError as url_e:
		print("No connection with grobid-service. Please check it is running on %s" % gburl)
	
	# liste de travail: grand tableau d'identifiants
	# (taille RAM: ~ 1GB pour 10 millions de doc)
	ids_ok = []
	
	
	################################################
	# Mode 1 : an ES query gets us the input IDs
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
		
		print("%s retrieved hits\n  of which %s without pdf" % (n_got, len(ids_sans_pdf)), file=stderr)
		
		# fermeture et suppression définitive du fichier tempo
		hit_file.close()
		remove(hit_file_path)
	
	################################################
	# Mode 2 : the IDs are provided on external list
	#          (no checks)
	elif args.list_in:
		filehandle = open(args.list_in)
		ids_ok = [line.rstrip() for line in filehandle]
		filehandle.close()
	#######
	
	
	# dans tous les cas : traitement de la liste ids_ok
	print(' ==> %s documents à traiter' % len(ids_ok))
	
	if args.yes:
		utilisateur = "y"
	else:
		utilisateur = input("ok pour lancer le traitement ? (y/n) ")
	
	if utilisateur in ['N', 'n', 'q']:
		print("Traitement annulé", file=stderr)
		exit()
	else:
		# quelques infos utiles
		timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
		info_str = grobid_models_info()
		print('pour info, paramètres du balisage\n  timestamp:%s\n  models:%s' %
		       (timestamp, info_str), file=stderr)
		
		# lancement
		
		# ===== get_grobid_bibs() en parallèle =============
		process_pool = Pool(int(CONF['process']['ncpu']))
		process_pool.map(get_grobid_bibs, ids_ok)
		process_pool.close()
		# ==================================================
	
	
	# a posteriori: optional concatenation of XMLs >> TEICorpus
	if args.group_output:
		teico = open("mon.teiCorpus.xml", "w")
		# un header pour tous
		global_header = """<?xml version="1.0" encoding="UTF-8" ?>
<teiCorpus xml:id="%s">
 <teiHeader>
  <fileDesc>
   <titleStmt>
    <respStmt>
     <resp>Extraction Refbib</resp>
     <name>
       grobid.v.0.3.4
       %s
     </name>
    </respStmt>
   </titleStmt>
   <publicationStmt>
    <distributor>ISTEX</distributor>
   </publicationStmt>
  </fileDesc>
 </teiHeader>""" % ("refbibs-enrich-"+timestamp, info_str)
		print(global_header, file=teico)
		for idi in ids_ok:
			this_path = path.join(
							CONF['output']['dir'],
							idi + CONF['output']['tei_ext']
						)
			try:
				this_tei = open(this_path, 'r')
			except FileNotFoundError as fnfe:
				# ECRITURE <TEI/> VIDE SI DOCUMENT ABSENT
				print(" <TEI xml:id=\"istex-%s\"/>" % idi, file=teico)
				continue
			# COPIE SI DOCUMENT PLEIN
			teico.write(this_tei.read())
			this_tei.close()
		
		# footer
		print("</teiCorpus>", file=teico)
		
		# voilà
		teico.close()
