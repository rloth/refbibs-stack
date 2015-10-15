#! /usr/bin/python3
"""
Structured bibliographic refs => structured queries => filter => link
"""

from lxml import etree
from libconsulte import api
from re import search, sub, MULTILINE

from os import listdir,path
from json import dumps

from random import shuffle

from sys import stderr, argv

# ---------------------------------

TEST = True


TEI_TO_LUCENE_MAP = {
	# attention parfois peut-être series au lieu de host dans la cible ?
	
	'analytic/title[@level="a"][@type="main"]'   : 'title', 
	'monogr/title[@level="m"][@type="main"]'  : 'title',  # main et type=m <=> monogr entière
	
	'monogr/imprint/date[@type="published"]/@when' : 'publicationDate', 
	'monogr/imprint/biblScope[@unit="volume"]'     : 'host.volume', 
	'monogr/imprint/biblScope[@unit="vol"]'        : 'host.volume', 
	'monogr/imprint/biblScope[@unit="issue"]'      : "host.issue", 
	'monogr/imprint/biblScope[@unit="page"]/@to'   : 'host.page.last', 
	'monogr/imprint/biblScope[@unit="page"]/@from' : 'host.page.first', 
	'monogr/imprint/biblScope[@unit="pp"]/@to'     : 'host.page.last', 
	'monogr/imprint/biblScope[@unit="pp"]/@from'   : 'host.page.first', 
	
	'analytic/author/persName/surname'                  : 'author.name', 
	'analytic/author/persName/forename[@type="first"]'  : '__IGNORE__', 
	'analytic/author/persName/forename[@type="middle"]' : '__IGNORE__', 
	
	'monogr/title[@level="m"]' : 'host.title', 
	'monogr/title[@level="j"]' : 'host.title',
	'monogr/author/persName/surname'  : 'host.author.name',  # ou author.name si monogr entière
	'monogr/author/persName/forename[@type="first"]'  : '__IGNORE__', 
	'monogr/author/persName/forename[@type="middle"]' : '__IGNORE__', 
	
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
	if any_text is None:
		return ''
	else:
		return text_basic_wildcard(text_remove_s(any_text))

def record(records_dict, field_tag, str_value):
	"""
	#  par ex:    'monogr/title'         : ['super titre']
	#  par ex:    'analytic/author/persName/surname'    : ['Dupont','Durand']
	#  par ex:    'monogr/biblScope[@unit="page]/@from' : ['123']
	
	on n'enregistre une nouvelle valeur que si chaîne non vide
	"""
	
	if len(str_value):
		# si ce champ n'existe pas encore
		if field_tag not in records_dict:
			# nouvelle liste
			records_dict[field_tag] = [str_value]
		# autrement
		else:
			# ajout à la liste
			records_dict[field_tag].append(str_value)
			# (notamment liste nécessaire pour les author:name1... )
	
	# retour du dico mis à jours
	return records_dict



def b_subvalues(refbib_subtree):
	"""
	Parcourt un élément XML biblStruct et renvoie un dictionnaire
	des chemins élements internes (xpath) => valeurs
	"""
	
	# à remplir dict de listes
	xml_subtexts_by_field = {}
	# structure : src_path : [src_content]

	
	
	# warn("=== NB de sous-elts: %i ===" % len(refbib_subtree))
	
	for elt in refbib_subtree:
		
		# === cas particuliers === (tei à texte dans attributs)
		if elt.tag == 'date':
			field = mon_xpath(elt)+'/@when'
			value = elt.attrib['when']
			
			if value:
				str_value = text_to_query_fragment(value)
				# enregistrement
				xml_subtexts_by_field = record(xml_subtexts_by_field, field, str_value)
		
		elif elt.tag == 'biblScope' and elt.attrib['unit'] == 'page':
			# cas rare <biblScope unit="page">332</biblScope>
			if elt.text:
				field = mon_xpath(elt)+'/@from'
				str_value = text_to_query_fragment(elt.text)
				# enregistrement
				xml_subtexts_by_field = record(xml_subtexts_by_field, field, str_value)
			
			# cas normal <biblScope unit="page" from="329" to="396" />
			else:
				for bout in ['from', 'to']:
					if elt.attrib[bout]:
						field = mon_xpath(elt)+"/@%s"%bout
						value = elt.attrib[bout]
						str_value = text_to_query_fragment(elt.attrib[bout])
						# enregistrement
						xml_subtexts_by_field = record(xml_subtexts_by_field, field, str_value)
		# cas normaux
		else:
			if elt.text:
				field = mon_xpath(elt)
				str_value = text_to_query_fragment(elt.text)
				# enregistrement
				xml_subtexts_by_field = record(xml_subtexts_by_field, field, str_value)
		
	return xml_subtexts_by_field


def warn(a_string):
	"mon warn sur sys.stderr"
	print(a_string, file=stderr)

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
				'host.page.first',
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
# bibfiles = ['/home/loth/refbib/a_annoter/2015-10-06_15h30-output_bibs.dir/D9F4D9BD6AB850E676DD80D89D3FD2773585B2A1.refbibs.tei.xml']

try:
	my_dir = argv[1]
except:
	warn("veuillez indiquer un dossier de sorties de grobid en argument")
	exit(1)

try:
	bibfiles = [path.join(my_dir,fi) for fi in listdir(my_dir)]
except:
	warn("le dossier %s n'existe pas" % my_dir)
	exit(1)

if TEST:
	# pour les tests (on fait 3 docs différents à chaque fois)
	shuffle(bibfiles)
	the_files = bibfiles[0:3]

	warn("= + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + =")
	warn("TEST_FILES %s" % the_files)
else:
	the_files = bibfiles

# lecture pour chaque doc => pour chaque bib
for bibfile in the_files:
	tei_dom = etree.parse(bibfile) 
	bib_elts = tei_dom.xpath('//listBibl/biblStruct')
	
	nb = len(bib_elts)
	if not len(bib_elts):
		warn("-- DOC %s: aucune bib --" % bibfile)
		continue
	else:
		warn("-- DOC %s: query %i bibs --" % (bibfile,nb))
	
	
	for i, refbib in enumerate(bib_elts):
		
		# chaque élément du sous-arbre
		subelts = [xelt for xelt in refbib.iter()]
		
		# ------ <verbose>
		warn("---------> contenus de la BIB GROBIDISÉE %s <--------" % str(i+1))
		for xelt in subelts:
			text = text_to_query_fragment(xelt.text)
			if len(text):
				print("  %s: %s" % (mon_xpath(xelt),text))
		# ------ </verbose>
		
		
		# ==================================================
		#          F I L T R E S    E N    A M O N T
		# ==================================================
		
		has_analytic = False
		has_super_long_title = False
		
		
		# (1)
		# Test simpliste monographie ou entrée analytique #
		for filles in refbib:
			# parcours rapide des branches niveau 1
			if filles.tag == 'analytic':
				has_analytic = True
				break
		
		# (2)
		# Test longueur du titre a (l'erreur la plus courante de grobid bibfields si biblines s'est trompé)
		my_titre_a_hits = refbib.xpath("/analytic/title[level='a']")
		if len(my_titre_a_hits):
			my_titre_a = my_titre_a_hits.pop()
			nb_chars_titre = len(my_titre_a)
			# seuil 250 déjà bien large mais parfois titre + nom conférence peut faire autant
			if nb_chars_titre > 300:
				has_super_long_title = True
		
		
		if has_super_long_title:
			warn("WARNING: (skip) Refbib a un titre hors-calibre (%i chars) '%s'" % (nb_chars_titre,my_titre_a))
			continue
		
		if not has_analytic:
			warn("WARNING: (skip) Refbib = monographie (ne peut exister dans la base)")
			continue
		
		
		# methode 1: recherche bag-of-words -----------------------------
		rb_liste_pleins = [t for t in b_text_to_bow(refbib) if len(t)]
		
		# warn(rb_liste_pleins)
		
		rb_query_1 = q=" ".join(rb_liste_pleins)            ## QUERY
		rb_answer_1 = get_top_match_or_None(rb_query_1)     ## ANSWER
		
		
		# méthodes 2 et 3 => on utilise les champs structurés -----------
		# on prend tout ce qui est intéressant dans le XML
		# sous la forme champ(=xpath):valeur(=texte)
		
		bib_dico_vals = b_subvalues(subelts)   # <=== iter + annot
		
		# construction requête structurée
		all_whole_query_fragments = []             # m2 et m3
		longer_tokenized_query_fragments = []      # m5
		m6_should_tokenized_query_fragments = []      # m6
		m6_must_tokenized_query_fragments = []        # m6
		for field in bib_dico_vals:
			for value in bib_dico_vals[field]:
				# obtention du champ api correspondant à notre sous-élément XML
				#             "---------"                     <--/----/----/@...
				# £TODO mapping encore un peu simpliste
				try:
					champ_api = TEI_TO_LUCENE_MAP[field]         # <=== mapping
				except KeyError:
					warn("WARNING: champ '%s' absent de la table TEI_TO_LUCENE_MAP" % field)
					champ_api = '_CHAMP_INCONNU_'
				
				# --- lucene query chunks ------------------------
				
				# cas non-structuré <<<<<<<<<<<<<<<<<<
				if champ_api == '_CHAMP_INCONNU_':
					# pour les méthodes 2 et 3 on garde entre guillemets
					query_whole_frag = '"'+value+'"'
					
					# liste de tous les fragments entiers
					all_whole_query_fragments.append(query_whole_frag)
					
				
				# on ignore les prénoms
				elif champ_api == '__IGNORE__':
					continue
				
				# on a un champ structuré <<<<<<<<<<<<<
				else:
					# pour les méthodes 2 et 3 on garde le fragment entier
					#                  ---------     -------
					query_whole_frag = champ_api+':"'+value+'"'
					#                  ---------     -------
					#                   champ      valeur texte entière
					
					# liste de tous les fragments entiers
					all_whole_query_fragments.append(query_whole_frag)
					
					# pour la méthode 5 chaque mot > 3, dans une liste groupée entre parenthèse
					
					filtered_toks = []
					for tok in value.split(' '):
						# champs ayant le droit d'être courts
						if champ_api in ['host.volume', 'host.issue','host.page.first','host.page.last']:
							filtered_toks.append(tok)
						# champs suffisemment longs
						elif len(tok) > 3:
							filtered_toks.append(tok)
					
					# si jamais il ne reste plus rien
					if not(len(filtered_toks)):
						warn("WARNING: filtrage des tokens courts a tout supprimé (valeur d'origine: '%s')" % query_whole_frag)
					
					
					# cas normal : re-jonction
					else:
						# cas solo
						if len(filtered_toks) == 1:
							query_tokenized_frag = champ_api+':'+filtered_toks[0]
						# cas avec parenthèses
						else:
							query_tokenized_frag = champ_api+':('+' '.join(filtered_toks)+')'
						
						# liste de tous les fragments filtrés et avec leur champs
						longer_tokenized_query_fragments.append(query_tokenized_frag)
					
					# et idem en stockant expressement 2 listes: les champs "MUST" | SHOULD pour la méthode 6
					if champ_api == 'publicationDate':
						m6_must_tokenized_query_fragments.append(query_tokenized_frag)
					else:
						m6_should_tokenized_query_fragments.append(query_tokenized_frag)
		
		# methode 2: recherche structurée stricte ---------------------------
		rb_query_2 = " AND ".join(all_whole_query_fragments)   ## QUERY 2
		
		# méthode 3 plus souple: pas de AND cette fois-ci -------------------
		rb_query_3 = " ".join(all_whole_query_fragments)       ## QUERY 3
		
		# méthode 5 : pas de AND, pas de guillemets + filtrage des tokens les plus courts
		# (évite match par les initiales de prénoms -- peu significatives!)
		rb_query_5 = " ".join(longer_tokenized_query_fragments)       ## QUERY 5
		
		# méthode 6 comme 5 mais retour d'un petit peu de strict :
		# (la date redevient obligatoire)
		rb_query_6 = None
		# TODO : pourquoi le "+" de lucene ne fonctionne pas ?
		if len(m6_must_tokenized_query_fragments):
			rb_query_6 = "("+" AND ".join(m6_must_tokenized_query_fragments)+") AND ("+" ".join(m6_should_tokenized_query_fragments)+")"
		
		
		# temporaire, réaffiché après la réponse api
		warn("Q2: %s" % rb_query_2)
		warn("Q3: %s" % rb_query_3)
		warn("Q5: %s" % rb_query_5)
		if rb_query_6:
			warn("Q6: %s" % rb_query_6)
		
		
		try:
			# API requests => json hits => dict -------------------------------
			rb_answer_2 = get_top_match_or_None(rb_query_2)     ## ANSWER 2
			rb_answer_3 = get_top_match_or_None(rb_query_3)     ## ANSWER 3
			rb_answer_5 = get_top_match_or_None(rb_query_5)     ## ANSWER 5
			if rb_query_6:
				rb_answer_6 = get_top_match_or_None(rb_query_6)     ## ANSWER 6
			else:
				rb_answer_6 = "Pas de date -- nécessaire pour la méthode 6"
			# -----------------------------------------------------------------
			
			# Sortie listing pour évaluation humaine CLI
			print(
			  "======================================\n",
			  "DOC %s -- BIB %s\n" % (bibfile, str(i+1)),
			  "------\nméthode 1\n requête:%s\n match:%s\n" % (rb_query_1, rb_answer_1),
			  "---\nméthode 2\n requête:%s\n match:%s\n" % (rb_query_2, rb_answer_2),
			  "---\nméthode 3\n requête:%s\n match:%s\n" % (rb_query_3, rb_answer_3),
			  "---\nméthode 5\n requête:%s\n match:%s\n" % (rb_query_5, rb_answer_5),
			  "---\nméthode 6\n requête:%s\n match:%s\n" % (rb_query_6, rb_answer_6),
			  )
		except Exception as e:
			warn("WARNING skip car exception % e" % str(e))


warn("liste des fichier PDF SOURCE de l'enrichissement traité :")
for bibfile in the_files:
	print (sub('\.refbibs\.tei\.xml','.pdf', bibfile))