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

# ---------------------------------
def b_text_to_query_fragments(refbib):
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

def b_subtags_print():
	for elt in refbib.iter():
		# on remplace les None par ''
		elt_text = elt.text if elt.text else ''
		
		# observés: que (saut de ligne + espaces)
		#  ** mais en théorie pas toujours **
		# => on le garde encore un petit moment
		elt_tail = elt.tail if elt.tail else ''
		
		# tout texte matchable
		alltext =  elt_text + elt_tail
		
		flat_alltext = text_remove_s(alltext)
		if len(flat_alltext):
			print("%s: '%s'" % (elt.tag, flat_alltext))
			for k in elt.attrib:
				if k in ['type','level','when','unit']:
					print("  @%s: %s" % (k, elt.attrib[k]))
				else:
					print("  >> attribut inconnu << @%s:..." % k)



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


# ----------------------------------

# 200 docs, 6588 refbibs en sortie de bib-get
bibfiles = listdir('./mes_200.output_bibs.d')

# pour les tests (faire des données différentes chaque fois)
shuffle(bibfiles)
ten_test_files = bibfiles[0:10]

# lecture pour chaque doc => pour chaque bib
for file in ten_test_files:
	tei_dom = etree.parse('mes_200.output_bibs.d/'+file) 
	bib_elts = tei_dom.xpath('//listBibl/biblStruct')
	for refbib in bib_elts:
		
		# methode 1: recherche bag-of-words
		rb_liste_pleins = [t for t in b_text_to_query_fragments(refbib) if len(t)]
		print(rb_liste_pleins)
		rb_query = q=" ".join(rb_liste_pleins)
		rb_top_answer = api.search(
			rb_query, 
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
			)[0]
		
		print(dumps(rb_top_answer, indent=2))

