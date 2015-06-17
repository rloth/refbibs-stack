#! /usr/bin/python3
"""
Client for bibliographical annotator grobid-service
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2015 INIST-CNRS (ISTEX project)"
__license__   = "LGPL ? TODO vérifier"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

import sys
import re
import json
import argparse
from urllib.parse import quote
from urllib.request import urlopen
from urllib.error import HTTPError
from multiprocessing import Pool

# temporairement: la config en dur
my_config = dict()
my_config['api_host']     = "api.istex.fr"
my_config['search_route'] = "/document/"
my_config['ncpu']   = 7
my_config['dir']   = 'mes_sorties_bib_tei'


def prepare_arg_parser():
	"""Preparation argument parser de l'input pour main"""
	parser = argparse.ArgumentParser(
		description="Client for bibliographical annotator grobid-service",
		usage="bib-get.py -q 'lucene query'",
		epilog="- © 2014-15 Inist-CNRS (ISTEX) romain.loth at inist.fr -"
		)
	
	parser.add_argument('-q','--query',
		metavar='"hawking AND corpusName:nature AND pubdate:[1970 TO *]"',
		help="a lucene query to pass to the api, for retrieval of all bibs of all hits",
		type=str,
		required=True,
		action='store')
	
	parser.add_argument('-m','--maxi',
		metavar='100',
		help="a maximum limit of processed docs (if the query returned more hits, the remainder will be ignored",
		type=int,
		default=None ,  # cf juste en dessous
		action='store')
	
	parser.add_argument('-d','--debug',
		metavar=1,
		type=int,
		help='logging level for debug info in [0-3]',
		default=0,
		action='store')
	
	return parser


def get(my_url):
	"""Get remote url *that contains a json* and parse it"""
	remote_file = urlopen(my_url)
	result_str = remote_file.read().decode('UTF-8')
	remote_file.close()
	json_values = json.loads(result_str)
	return json_values


def api_search(q, config=my_config, limit=None):
	"""
	Get concatenated hits array from json results of a lucene query on ISTEX api.
	
	Keyword arguments:
	   q       -- a lucene query
	              ex: "hawking AND corpusName:nature AND pubdate:[1970 TO *]"
	   config  -- dict of config values as per 'bib-get.config' file (ini-like)
	
	the config dict should contain all 3 following values:
	   config[api_host]      -- ex: "api.istex.fr"
	   config[search_route]  -- ex: "/document/"
	   config[out_fields]    -- ex: "corpusName,pubdate,fulltext,title"
	
	Output format is a parsed json with a total value and a hit list:
	{ 'hits': [ { 'id': '21B88F4EFBA46DC85E863709CA9824DEED7B7BFC',
				  'title': 'Recovering information borne by quanta that '
						   'crossed the black hole event horizon'},
				{ 'id': 'C095E6F0A43EBE3E98E2E6E17DD8775617636034',
				  'title': 'Holographic insights and puzzles'}],
	  'total': 2}
	"""
	
	safe_lucene_query = quote(q)
	
	# construction de l'URL:
	# 'https://' + $HOST + $SEARCH_ROUTE 
	#  + '?q=' + LUCENE_QUERY + '&output=' + OUT_FIELDS
	base_url = 'https:' + '//' + config['api_host'] + config['search_route'] + '?' + 'q=' + safe_lucene_query + '&output=' + "fulltext,title"
	
	# requête initiale pour le décompte
	count_url = base_url + '&size=1'
	resp_values = get(count_url)
	n_docs = int(resp_values['total'])
	print('%s documents trouvés' % n_docs)
	
	# limitation éventuelle fournie par le switch --maxi
	if limit is not None:
		n_docs = limit
	
	# la liste des résultats à renvoyer
	all_hits = []
	
	# ensuite 2 cas de figure : 1 requête ou plusieurs
	if n_docs <= 5000:
		# requête simple
		my_url = base_url + '&size=%i' % n_docs
		resp_values = get(my_url)
		all_hits = resp_values['hits']
	
	else:
		# requêtes paginées pour les tailles > 5000
		print("Collecting result hits... ")
		for k in range(0, n_docs, 5000):
			print("%i..." % k)
			my_url = base_url + '&size=5000' + "&from=%i" % k
			resp_values = get(my_url)
			all_hits += resp_values['hits']
		
		# si on avait une limite par ex 7500 et qu'on est allés jusqu'à 10000
		all_hits = all_hits[0:n_docs]
	
	return(all_hits)


def get_grobid_bibs(istex_id):
	"""
	Calls grobid-service GET route /processReferencesViaUrl?pdf_url= allowing to process remote PDFs (eg from istex api)
	
	The pdfs urls always have the form:
	https://api.istex.fr/document/<HERE_ISTEX_ID>/fulltext/pdf
	
	Unique non-kw argument:
	   istex_id  -- ex:21B88F4EFBA46DC85E863709CA9824DEED7B7BFC
	
	Returns the TEI generated by grobid-service annotator
	"""
	
	
	# construction requête grobid en GET
	tei_url = "http://vp-istex-grobid.intra.inist.fr:8080/processReferencesViaUrl?pdf_url=https://api.istex.fr/document/%s/fulltext/pdf" % istex_id
	
	try:
		# interrogation ========================
		grobid_answer_content = urlopen(tei_url)
		# ======================================
		
		# urlopen a renvoyé un objet file-like
		result = grobid_answer_content.read()
		grobid_answer_content.close()
		result_tei = result.decode('UTF-8')
		
		# on remplace l'entête
		if len(result_tei):
			result_tei = re.sub('<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xlink="http://www.w3.org/1999/xlink" \n xmlns:mml="http://www.w3.org/1998/Math/MathML">', 
			                    '<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xlink="http://www.w3.org/1999/xlink" xml:id="istex-%s">' % istex_id,
			                    result_tei)
		
		# SORTIE > fichier tei individuel  ID.refbibs.tei.xml
		out_file = open(my_config['dir']+'/'+istex_id+'.refbibs.tei.xml', 'w')
		out_file.write(result_tei)
		out_file.close()
		
	except HTTPError as e:
		print ("HTTP error %s on %s: skip" % (e.code, istex_id),
		        file=sys.stderr)
	




########################################################################
########################################################################
########################################################################
if __name__ == '__main__':
	
	parser = prepare_arg_parser()
	args = parser.parse_args(sys.argv[1:])
	
	hits = api_search(q=args.query, limit=args.maxi)

	n_got = len(hits)
	
	# grande liste d'identifiants
	ids_ok = []
	ids_sans_pdf = []
	
	# on lit/vérifie les réponses et on les mets dans la liste
	for hit in hits:
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
	
	print('dont %s retenus pour traitement\n  dont %s sans pdf\n ==> %s restant à traiter' % (n_got, len(ids_sans_pdf), len(ids_ok)))
	
	utilisateur = input("ok pour lancer le traitement ? ")
	
	if utilisateur in ['N', 'n', 'q']:
		exit()
	else:
		process_pool = Pool(my_config['ncpu'])
		process_pool.map(get_grobid_bibs, ids_ok)
