#! /usr/bin/python3
"""
Structured bibliographic refs => structured queries => filter => link
"""

from lxml import etree
from libconsulte import api
from re import search, sub, MULTILINE

from os import listdir

# ---------------------------------
def b_text_list(refbib):
	"""
	imprime juste les textes pour bag-of-words
	/!\ pas les attributs !! comme date@when /!\
	"""
	bow_list = [text_remove_s(txt) for txt in refbib.itertext() if txt is not None]
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

# '~' est souvent un retour d'OCR signalant les caras incompris
# ex: J. ams. ten. Pkys. Bl~sdell ~blishi~8 Company Tellus J. atmos. ten. Phys


# matchs avec \w
#  => match('\w+', "ǌork_alldédalö")
#    AOK: <_sre.SRE_Match object; span=(0, 14), match='ǌork_alldédalö'>
#  => match('\w+', "Jo¨rgensen")
#    NON: <_sre.SRE_Match object; span=(0, 2), match='Jo'>



# "Am Heart J" => "American Heart Journal"
# strict: host.title:Am* AND host.title:Heart*
# souple: host.title:Am* host.title:Heart*


# bag of words
# score_filtres + bag of words ??
# structurés
# score_filtres + structurés
# score_filtres + structurés + sous-ensembles std
# score_filtres + structurés + sous-ensembles selon type

# filtres:
#  - longueur du titre
#  - caractères interdits dans le nom/prénom
#  - nombre de nom/prénoms


# ----------------------------------

# 200 docs, 6588 refbibs en sortie de bib-get
bibfiles = listdir('./mes_200.output_bibs.d')

# lecture pour chaque doc => pour chaque bib
for file in bibfiles:
	tei_dom = etree.parse('mes_200.output_bibs.d/'+file) 
	bib_elts = tei_dom.xpath('//listBibl/biblStruct')
	for refbib in bib_elts:
		
		# methode 1: recherche bag-of-words
		rb_liste_pleins = [t for t in b_text_list(refbib) if len(t)]
		print(rb_liste_pleins)
		rb_query = q=" ".join(rb_liste_pleins)
		rb_top_answer = api.search(
			rb_query, 
			limit=1,
			outfields=['id', 'title', 'host.title', 'host.volume']
			)[0]
		
		print(rb_top_answer)

