#! /usr/bin/python3
"""
Structured bibliographic refs => structured queries => filter => link
"""

from lxml import etree
from libconsulte import api
from re import search, sub, MULTILINE

from os import listdir
from json import dumps

from random import shuffle

from sys import stderr

# ---------------------------------


TEI_TO_LUCENE_MAP = {
	# attention parfois peut-être series au lieu de host dans la cible ?
	
	'analytic/title[@level="a"][@type="main"]'   : 'title', 
	'monogr/title[@level="m"][@type="main"]'  : 'title',  # main et type=m <=> monogr entière
	
	'monogr/imprint/date[@type="published"]/@when' : 'publicationDate', 
	'monogr/imprint/biblScope[@unit="volume"]'     : 'host.volume', 
	'monogr/imprint/biblScope[@unit="issue"]'      : "host.issue", 
	'monogr/imprint/biblScope[@unit="page"]/@to'   : 'host.page.last', 
	'monogr/imprint/biblScope[@unit="page"]/@from' : 'host.page.first', 
	
	'analytic/author/persName/surname'                  : 'author.name', 
	'analytic/author/persName/forename[@type="first"]'  : 'author.name', 
	'analytic/author/persName/forename[@type="middle"]' : 'author.name', 
	
	'monogr/title[@level="m"]' : 'host.title', 
	'monogr/title[@level="j"]' : 'host.title',
	'monogr/author/persName/surname'  : 'host.author.name',  # ou author.name si monogr entière
	'monogr/author/persName/forename[@type="first"]'  : 'host.author.name', 
	'monogr/author/persName/forename[@type="middle"]' : 'host.author.name', 
	
	'monogr/meeting'    : 'host.conference.name', 
	
	'monogr/editor'              : 'host.editor',           # ou 'editor' si monogr entière , 
	'monogr/imprint/publisher'   : 'host.editor', 
	# 'monogr/imprint/pubPlace'    :  ???, 

	'note'     : '_CHAMP_INCONNU_', 
	'monogr/meeting/address/addrLine'  : '_CHAMP_INCONNU_', 

	# non observés dans la sortie grobid mais existants dans les natives 2 TEI, 
	# 'idno[@type="DOI"]'  etc
	
	# remarque:
	# pour l'instant les deux cas analytic+monogr ET monogr entière SONT dans la même table
	# => todo distinguer 2 cas en amont et 2 tables pour les éléments qui changent de sens
	#    (eg. monogr/author ==> en général q=host.author.name:... mais q=author.name:... si monographie entière seule
	#    (mais suffisant actuellement car monographie entière seule est extremmement rare dans ISTEX)
}


def mon_xpath(xelt, relative_to = "biblStruct"):
	"""Récupéré de libtrainers rag_xtools
	   version sans namespaces mais avec 
	   quelques attributs utiles"""
	# starting point
	the_path = tag_n_useful_attrs(xelt)
	if the_path == relative_to:
		return "."
	else:
		# ancestor loop
		for pp in xelt.iterancestors():
			if pp.tag != relative_to:
				# prepend elts on the way
				the_path = tag_n_useful_attrs(pp) + "/" + the_path
			else:
				# reached chosen top elt
				break
	# voilà
	return the_path

def tag_n_useful_attrs(xelt, my_useful_attrs=['type','level','unit']):
	"""
	       INPUT                    |       OUTPUT
	--------------------------------|---------------------
	XMLElement(author@trucid=lkflk)=|> 'author'
	XMLElement(title @level=j)     =|> 'title[@level="j"]'
	
	attributs jugés utiles : @type, @level, @unit
	            (c'est prévu pour des tei:biblStruct)
	"""
	xtag_str = xelt.tag
	for k in xelt.attrib:
		if k in my_useful_attrs:
			xtag_str += '[@%s="%s"]' % (k, xelt.attrib[k])
	
	return xtag_str


def b_text_to_bow(refbib):
	"""
	imprime juste les textes pour bag-of-words
	/!\ et les 3 attributs connus comme importants /!\
	     - date/@when
	     - biblScope[@unit='page']/@from
	     - biblScope[@unit='page']/@to
	"""
	
	# tous sauf les attributs et les textes vides
	bow_list = [text_remove_s(txt) for txt in refbib.itertext() if txt is not None]
	
	# les 3 attributs voulus
	when = refbib.xpath('monogr/imprint/date/@when')
	if len(when):
		bow_list.append(text_to_query_fragment(when[0]))
	
	pfrom = refbib.xpath('monogr/imprint/biblScope[@unit="page"]/@from')
	if len(pfrom):
		bow_list.append(text_to_query_fragment(pfrom[0]))
	
	pto = refbib.xpath('monogr/imprint/biblScope[@unit="page"]/@to')
	if len(pto):
		bow_list.append(text_to_query_fragment(pto[0]))
	return bow_list


def text_remove_s(all_text):
	"""
	removes trailing spaces and newlines
	"""
	# on n'agit que s'il y a au moins un cara plein
		# => pas les elts vides, ni \s dont saut de ligne
	if len(all_text) and search('[^\s]', all_text, flags=MULTILINE):
		flat_alltext = sub(r'\n', '¤', all_text, flags=MULTILINE)
		flat_alltext = sub(r'[¤\s]+$', '', flat_alltext)
		flat_alltext = sub(r'^[¤\s]+', '', flat_alltext)
	else:
		flat_alltext = ''
	return flat_alltext

def text_basic_wildcard(any_text):
	"""
	Replaces '~' by '?' (from OCR convention to lucene query wildcard)
	
	# Explication
	# '~' est souvent un retour d'OCR signalant les caras incompris
	# ex: J. ams. ten. Pkys. Bl~sdell ~blishi~8 Company Tellus J. atmos. ten. Phys
	
	# '?' est le caractère joker qui correspond à la même idée dans le monde des requêtes lucene
	"""
	return sub('~', '?', any_text)

def text_to_query_fragment(any_text):
	return text_basic_wildcard(text_remove_s(any_text))


def b_subvalues(refbib_subtree):
	"""
	Parcours un élément XML biblStruct et renvoie un dictionnaire
	des chemins élements internes (xpath) => valeurs
	"""
	
	# à remplir
	records_dict = {}
	# structure : src_path               : src_content
	#  par ex:    'monogr/title'         : 'super titre'
	#  par ex:    'analytic/author/persName/surname'    : 'Dupont'
	#  par ex:    'monogr/biblScope[@unit="page]/@from' : 123
	
	
	# print("=== NB de sous-elts: %i ===" % len(refbib_subtree))
	
	for elt in refbib_subtree:
		
		# === cas particuliers === (tei à texte dans attributs)
		if elt.tag == 'date':
			field = mon_xpath(elt)+'/@when'
			value = elt.attrib['when']
			
			if value:
				str_value = text_to_query_fragment(value)
				# enregistrement
				if len(str_value):
					records_dict[field] = str_value
		
		elif elt.tag == 'biblScope' and elt.attrib['unit'] == 'page':
			# cas rare <biblScope unit="page">332</biblScope>
			if elt.text:
				field = mon_xpath(elt)+'/@from'
				str_value = text_to_query_fragment(elt.text)
				# enregistrement
				if len(str_value):
					records_dict[field] = str_value
			
			# cas normal <biblScope unit="page" from="329" to="396" />
			else:
				for bout in ['from', 'to']:
					if elt.attrib[bout]:
						field = mon_xpath(elt)+"/@%s"%bout
						value = elt.attrib[bout]
						str_value = text_to_query_fragment(elt.attrib[bout])
						# enregistrement
						if len(str_value):
							records_dict[field] = str_value
		# cas normaux
		else:
			if elt.text:
				field = mon_xpath(elt)
				str_value = text_to_query_fragment(elt.text)
				# enregistrement
				if len(str_value):
					records_dict[field] = str_value
		
	return records_dict


def get_top_match_or_None(solving_query):
	"""
	ISTEX-API search for refbib resolution
	=> output = human-readble string for evaluation
	"""
	my_matches = api.search(
			solving_query, 
			limit=1,
			outfields=['id', 
				'title',
				'host.title',
				'host.volume',
				'publicationDate',
				'author.name',
				'corpusName',
				'doi'
				]
			)
	if len(my_matches):
		# json human readable string
		return dumps(my_matches[0], indent=2)
	else:
		return "PAS DE MATCH"
	


# Rappels:

# (1) MATCHING

# matchs avec \w
#  => match('\w+', "ǌork_alldédalö")
#    AOK: <_sre.SRE_Match object; span=(0, 14), match='ǌork_alldédalö'>
#  => match('\w+', "Jo¨rgensen")
#    NON: <_sre.SRE_Match object; span=(0, 2), match='Jo'>

# "Am Heart J" => "American Heart Journal"
# strict: host.title:Am* AND host.title:Heart*
# souple: host.title:Am* host.title:Heart*

# (2) METHODES TESTABLES
# bag of words
# score_filtres + bag of words ??
# structurés
# score_filtres + structurés
# score_filtres + structurés + sous-ensembles std
# score_filtres + structurés + sous-ensembles selon type

# (3) filtres:
#  - longueur du titre
#  - caractères interdits dans le nom/prénom
#  - nombre de nom/prénoms


# -------------------------------------
# MAIN création d'un jeu d'évaluation
# -------------------------------------

# 200 docs, 6588 refbibs en sortie de bib-get
bibfiles = listdir('./mes_200.output_bibs.d')

# pour les tests (on fait 10 ou 20 docs différents à chaque fois)
shuffle(bibfiles)
ten_test_files = bibfiles[0:20]

# lecture pour chaque doc => pour chaque bib
for file in bibfiles:
	tei_dom = etree.parse('mes_200.output_bibs.d/'+file) 
	bib_elts = tei_dom.xpath('//listBibl/biblStruct')
	
	for i, refbib in enumerate(bib_elts):
		
		subelts = [xelt for xelt in refbib.iter()]
		
		# ------ verbose
		#for xelt in subelts:
		#	print("%s: %s" % (tag_n_useful_attrs(xelt),xelt.text), file=stderr)
		
		
		
		# methode 1: recherche bag-of-words -----------------------------
		rb_liste_pleins = [t for t in b_text_to_bow(refbib) if len(t)]
		
		# print(rb_liste_pleins)
		
		rb_query_1 = q=" ".join(rb_liste_pleins)            ## QUERY
		rb_answer_1 = get_top_match_or_None(rb_query_1)     ## ANSWER
		
		
		# méthodes 2 et 3 => on utilise les champs structurés -----------
		# on prend tout ce qui est intéressant dans le XML
		# sous la forme champ(=xpath):valeur(=texte)
		
		bib_dico_vals = b_subvalues(subelts)   # <=== iter + annot
		
		# construction requête structurée
		full_query_fragments = []
		for field in bib_dico_vals:
			# obtention du champ api corrspondant à notre sous-champ XML
			
			try:
				# £TODO mapping encore un peu simpliste
				champ_api = TEI_TO_LUCENE_MAP.get(field, '_CHAMP_INCONNU_')  # <=== mapping
			except KeyError as kerr:
				print(kerr.string)
			
			# lucene query chunks
			if champ_api == '_CHAMP_INCONNU_':
				query_frag = '"'+bib_dico_vals[field]+'"'
			
			# on a un champ structuré
			else:
				#            ---------     ---------------------
				query_frag = champ_api+':"'+bib_dico_vals[field]+'"'
				#            ---------     ---------------------
				#             champ          valeur texte
			
			# liste de tous les fragments
			full_query_fragments.append(query_frag)
		
		# methode 2: recherche structurée stricte -----------------------
		rb_query_2 = q=" AND ".join(full_query_fragments)   ## QUERY 2
		rb_answer_2 = get_top_match_or_None(rb_query_2)     ## ANSWER 2
		
		# méthode 3 plus souple: pas de AND cette fois-ci ---------------
		rb_query_3 = q=" ".join(full_query_fragments)       ## QUERY 3
		rb_answer_3 = get_top_match_or_None(rb_query_3)     ## ANSWER 3
		
		
		# Sortie évaluation humaine
		print(
		  "======================================\n",
		  "DOC %s -- BIB %i\n" % (file, i+1),
		  "------\nméthode 1\n requête:%s\n match:%s\n" % (rb_query_1, rb_answer_1),
		  "---\nméthode 2\n requête:%s\n match:%s\n" % (rb_query_2, rb_answer_2),
		  "---\nméthode 3\n requête:%s\n match:%s\n" % (rb_query_3, rb_answer_3)
		  )


print("LISTE DES FICHIERS PDF source :")
for file in bibfiles:
	print (sub('\.refbibs\.tei\.xml','.pdf', file))