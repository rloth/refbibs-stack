#! /usr/bin/python3
"""
Structured bibliographic refs => structured queries => filter => link
"""

from lxml import etree
from libconsulte import api
from re import search, sub, MULTILINE, match

from re import split as resplit

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

	'note'     : '_NULL_', 
	'monogr/meeting/address/addrLine'  : '_NULL_', 

	# non observés dans la sortie grobid mais existants dans les natives 2 TEI, 
	# 'idno[@type="DOI"]'  etc
	
	# remarque:
	# pour l'instant les deux cas analytic+monogr ET monogr entière SONT dans la même table
	# => todo distinguer 2 cas en amont et 2 tables pour les éléments qui changent de sens
	#    (eg. monogr/author ==> en général q=host.author.name:... mais q=author.name:... si monographie entière seule
	#    (mais suffisant actuellement car monographie entière seule est extremmement rare dans ISTEX)
}



class BiblStruct(object):
	"""
	Groupe les méthodes pour un élément XML tei:biblStruct
	"""
	
	def __init__(self, xml_element_tree):
		"""
		Initialisation depuis le subtree XML lu par lxml.parse(tei_doc) puis lxml.find('biblStruct')
		"""
		
		# slot central: l'élément XML
		# ---------------------------
		self.etree = xml_element_tree
		
		
		# 3 dicts utilisés pour les transformations
		# ------------------------------------------
		
		# les chaines entières rangées par xpath source
		self.subvals = None
		
		# cf. bib_subvalues()
		
		
		# copie des même chaînes rangées par équiv. api
		#    et idem en tokenisant
		self.api_strs = None   
		self.api_toks = None   
		
		# cf. prepare_query_frags()
		
		
		# exemples:
		# ----------
		# self.subvals {
		#  'analytic/title[@level="a"][@type="main"]'        : ['Silent myocardial ischemia'], 
		#  'analytic/author/persName/surname'                : ['Cohn','Dupont'], 
		#  'analytic/author/persName/forename[@type="first"]': ['Pf','F']
		#  'monogr/title[@level="j"]'                        : ['Ann Intern Med'], 
		#  'monogr/imprint/date[@type="published"]/@when'    : ['1988'], 
		#  'monogr/imprint/biblScope[@unit="volume"]'        : ['109'], 
		#  'monogr/imprint/biblScope[@unit="page"]/@from'    : ['312'], 
		#  'monogr/imprint/biblScope[@unit="page"]/@to'      : ['317'], 
		#  } 

		# self.api_strs {
		#  'title'          : ['Silent myocardial ischemia'],
		#  'author.name'    : ['Cohn','Dupont'],
		#  'host.title'     : ['Ann Intern Med'],
		#  'publicationDate': ['1988'],
		#  'host.volume'    : ['109'],
		#  'host.page.first': ['312']
		#  'host.page.last' : ['317'],
		#  }
		
		# self.api_toks {
		#  'title'          : ['Silent', 'myocardial', 'ischemia'], 
		#  'author.name'    : ['Cohn', 'Dupont'], 
		#  'host.title'     : ['Ann', 'Intern', 'Med'], 
		#  'publicationDate': ['1988'], 
		#  'host.volume'    : ['109'], 
		#  'host.page.first': ['312']
		#  'host.page.last' : ['317'], 
		# }
		
		
	
	
	def to_bow(self):
		"""
		Renvoie juste les contenus textes pour bag-of-words
		/!\ et les 3 attributs connus comme importants /!\
			 - date/@when
			 - biblScope[@unit='page']/@from
			 - biblScope[@unit='page']/@to
		"""
		# tous sauf les attributs et les textes vides
		bow_list = [text_remove_s(txt) for txt in self.etree.itertext() if txt is not None]
		
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
	
	
	def prepare_query_frags(self):
		"""
		Construit self.api_strs et self.api_toks
		   (permettent d'utiliser les infos structurées
		    de l'elt XML dans une query API type Lucene)
		
		api_strs --- re-dispatch d'un dict de str[] provenant du XML 
		             vers un dict de str[] rangé par champs API
		
		api_toks --- même structure mais avec les chaînes de cara
		             tokenisées ' '.split et filtrées (len >= 4 sauf exceptions)
		             
		Utilise record() pour mettre à jour les dict en filtrant les [] et les [""]
		"""
		# dictionnaire {k => [strs]} d'expressions relevées
		# (rangé ici par xpath via préalable subvalues())
		for bibxpath in self.subvals:
			
			# traduction des clés
			# ex:    clef  => clé
			# ex: monogr/author/surname => host.author.name
			champ = self.xpath_to_api_field(bibxpath)
			
			# api_strs
			for whole_str in self.subvals[bibxpath]:
			
				# on ignore certaines valeurs (ex: les initiales de prénoms)
				if champ == '__IGNORE__':
					continue
				
				# on stocke en regroupant si nécessaire (cardinalité réduite)
				else:
					self.api_strs = self.record(self.api_strs, champ, whole_str)
			
		# maintenant que c'est bien rangé on repasse
		# pour api_toks --- idem avec re-tokenisation
		total_kept = 0
		for key in self.api_strs:
			for whole_str in self.api_strs[key]:
				# from re import split as resplit
				for tok in resplit(r'\W', whole_str):
					# print("TOK",tok)
					
					# champs ayant le droit d'être courts
					if key in ['host.volume', 'host.issue','host.page.first','host.page.last']:
						self.api_toks = self.record(self.api_toks, key, tok)
						total_kept += 1
					
					# champs ayant le droit à des tokens plus courts
					elif key in ['host.title', 'author.name'] and (len(tok) >= 2 or tok in ['j','J',']']):
						self.api_toks = self.record(self.api_toks, key, tok)
						total_kept += 1
					
					# autres champs: tokens suffisemment longs uniquement
					elif len(tok) >= 4:
						self.api_toks = self.record(self.api_toks, key, tok)
						total_kept += 1
						
		if total_kept == 0:
			warn("WARNING: filtrage des tokens courts a tout supprimé (valeurs d'origine: '%s')" % self.subvals)
		
		# voilà
		# self.api_strs rempli
		# self.api_toks rempli
		
	
	def bib_subvalues(self):
		"""
		iter + annot
		
		Parcourt un élément XML biblStruct et renvoie un dict
		          des chemins internes (xpath) => valeurs [chaînes texte]
		"""
		
		if not self.subvals:
		
			# à remplir dict de listes
			xml_subtexts_by_field = {}
			# structure : src_path : [src_content]
			
			# warn("=== NB de sous-elts: %i ===" % len(self.etree))
			
			for elt in self.etree.iter():
				
				# === cas particuliers ===
				# (tei à texte dans attributs)
				if elt.tag == 'date':
					field = mon_xpath(elt)+'/@when'
					value = elt.attrib['when']
					
					if value:
						str_value = text_to_query_fragment(value)
						# enregistrement
						xml_subtexts_by_field = self.record(xml_subtexts_by_field, field, str_value)
				
				elif elt.tag == 'biblScope' and elt.attrib['unit'] == 'page':
					# plutôt rare <biblScope unit="page">332</biblScope>
					if elt.text:
						field = mon_xpath(elt)+'/@from'
						str_value = text_to_query_fragment(elt.text)
						# enregistrement
						xml_subtexts_by_field = self.record(xml_subtexts_by_field, field, str_value)
					
					# plutôt courant <biblScope unit="page" from="329" to="396" />
					else:
						for bout in ['from', 'to']:
							if elt.attrib[bout]:
								field = mon_xpath(elt)+"/@%s"%bout
								value = elt.attrib[bout]
								str_value = text_to_query_fragment(elt.attrib[bout])
								# enregistrement
								xml_subtexts_by_field = self.record(xml_subtexts_by_field, field, str_value)
				
				# === cas normaux ===
				# (texte dans l'élément)
				else:
					if elt.text:
						field = mon_xpath(elt)
						str_value = text_to_query_fragment(elt.text)
						# souvent vide (non terminaux avec "\s+"
						# alors on filtre, même si record() l'aurait enlevé
						if str_value:
							# enregistrement
							xml_subtexts_by_field = self.record(xml_subtexts_by_field, field, str_value)
			
			# memoize
			self.subvals = xml_subtexts_by_field
		
		return self.subvals
		
		
	@staticmethod
	def record(records_dict, field_tag, str_value):
		"""
		Routine de création et màj de dict de forme: {clefs => ["str","str"...]}
		
		(updates dict of lists for BiblStruct.subvalues 
		                       and BiblStruct.prepare_query_frags)
		
		#  par ex:    'analytic/author/persName/surname'    : ['Dupont','Durand']
		#  par ex:    'monogr/title'                        : ['super titre']
		
		on n'enregistre une nouvelle valeur que si chaîne non vide
		"""
		
		# auto-vivification la première fois
		if records_dict is None:
			records_dict = {}
		
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
		
		# retour du dico mis à jour
		return records_dict
	
	
	@staticmethod
	def xpath_to_api_field(xpath_selector, mapping = TEI_TO_LUCENE_MAP):
		"""
		Convertisseur d'un type de sous-élément provenant du XML biblStruct
					  vers un couple (champ_api,[valeurs]) 
		
		Utilise une table comme:
			mapping = { 'monogr/imprint/date[@type="published"]/@when' : 'publicationDate', 
						'monogr/imprint/biblScope[@unit="volume"]'     : 'host.volume', 
						'monogr/imprint/biblScope[@unit="issue"]'      : "host.issue",
						(...)
						}
		"""
		
		try:
			champ_api = TEI_TO_LUCENE_MAP[xpath_selector]
		except KeyError:
			warn("WARNING: champ '%s' absent de la table TEI_TO_LUCENE_MAP" % field)
			champ_api = '_CHAMP_INCONNU_'
		
		return champ_api
	
	
	def an_check(self):
		"""
		Cherche analytic dans les premiers descendants
		"""
		for filles in self.etree:
			# parcours rapide des branches niveau 1
			if search(r'analytic$', filles.tag):
				return True
		return False


	def super_long_tit_check(self, too_many=300):
		"""
		Vérifie si le titre a une longueur anormale
		
		# explication seuil 300
		 200-250 déjà bien large mais parfois on a un
		 titre + nom conférence qui peut faire autant
		"""
		my_titre_a_hits = self.etree.xpath("/analytic/title[level='a']")
		if not len(my_titre_a_hits):
			return False
		else:
			my_titre_a = my_titre_a_hits.pop()
			return len(my_titre_a) > too_many


# ---------------------------------
#        X M L   T O O L S
# ---------------------------------

def mon_xpath(xelt, relative_to = "biblStruct"):
	"""Récupéré de libtrainers rag_xtools
	
	   version avec: tag_n_useful_attrs(elt) 
	     au lieu de: elt.tag
	"""
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
	# ex:  'monogr/imprint/biblScope[@unit="volume"]'
	return the_path


def tag_n_useful_attrs(xelt, my_useful_attrs=['type','level','unit']):
	"""
	tag sans namespaces mais avec ses attributs distinctifs
	par ex: biblScope[@unit="page"]
	
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


# ---------------------------------
#      T E X T    T O O L S
# ---------------------------------

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


# -------------------------------------
#  I / O    H E L P E R     F U N C S
# -------------------------------------

def warn(a_string):
	"mon warn sur sys.stderr"
	print(a_string, file=stderr)


def get_top_match_or_None(solving_query):
	"""
	ISTEX-API search for refbib resolution
	=> output = one json object or None
	#~ => output = human-readble string for evaluation
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
		return my_matches[0]
	else:
		return None


def some_docs(a_dir_path, test_mode=TEST):
	"""
	Simple liste de documents depuis fs
	(si test, on n'en prend que 3)
	"""
	try:
		bibfiles = [path.join(my_dir,fi) for fi in listdir(a_dir_path)]
	except:
		warn("le dossier %s n'existe pas" % a_dir_path)
		exit(1)

	if test_mode:
		# pour les tests (on fait 3 docs différents à chaque fois)
		shuffle(bibfiles)
		the_files = bibfiles[0:3]

		warn("= + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + = + =")
		warn("TEST_FILES %s" % the_files)
	else:
		the_files = bibfiles
	
	return the_files



# ------------------------------------------
# >  LES DIFFERENTES METHODES DE MATCHING  <
# ------------------------------------------

# 5 fonctions globalement semblables
# mais avec de légère variantes
#
# pour comparer leur résultat, elles seront toutes 
# appelées, grace à la liste query_funcs


def to_query_method_0_bow(bib_obj):
	"""
	requête baseline: bag of words
	"""
	# methode baseline: recherche bag-of-words ----------------
	rb_liste_pleins = [t for t in bib_obj.to_bow() if len(t)]
	
	# warn(rb_liste_pleins)
	q=" ".join(rb_liste_pleins)
	
	return q


def to_query_method_1_AND_quoted(bib_obj):
	"""
	requête entière stricte : valeurs entières unies par AND
	"""
	
	all_whole_query_fragments = []
	
	for champ_api in bib_obj.api_strs:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<
		if champ_api == '_NULL_':
			# on garde entre guillemets
			field_whole_frags = ['"'+value+'"' for value in bib_obj.api_strs[champ_api]]
			
			# liste de tous les fragments entiers
			all_whole_query_fragments += field_whole_frags
			
		
		# on a un champ structuré <<<<<<<<<<<<<
		# cas normal
		else:
			# on garde le fragment entier
			#                    ---------     -------
			field_whole_frags = [champ_api+':"'+value+'"' for value in bib_obj.api_strs[champ_api]]
			#                    ---------     -------
			#                     champ      valeur texte entière
			
			# liste de tous les fragments entiers
			all_whole_query_fragments += field_whole_frags
		
		# tests après chaque boucle
		#~ print("m1,2", all_whole_query_fragments)
	
	# methode 1: recherche structurée stricte ---------------------------
	q = " AND ".join(all_whole_query_fragments)   ## QUERY 1
	return q



def to_query_method_2_SHOULD_quoted(bib_obj):
	"""
	requête entière souple : valeurs entières unies par " "
	
	NB: seule la dernière ligne change par rapport à la méthode 1 /!\
	"""
	
	all_whole_query_fragments = []
	
	for champ_api in bib_obj.api_strs:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<
		if champ_api == '_NULL_':
			# on garde entre guillemets
			field_whole_frags = ['"'+value+'"' for value in bib_obj.api_strs[champ_api]]
			
			# liste de tous les fragments entiers
			all_whole_query_fragments += field_whole_frags
			
		
		# on a un champ structuré <<<<<<<<<<<<<
		# cas normal
		else:
			# on garde le fragment entier
			#                    ---------     -------
			field_whole_frags = [champ_api+':"'+value+'"' for value in bib_obj.api_strs[champ_api]]
			#                    ---------     -------
			#                     champ      valeur texte entière
			
			# liste de tous les fragments entiers
			all_whole_query_fragments += field_whole_frags
		
		# tests après chaque boucle
		#~ print("m1,2", all_whole_query_fragments)
	
	# méthode 2 plus souple: pas de AND cette fois-ci -------------------
	q = " ".join(all_whole_query_fragments)       ## QUERY 2
	return q



def to_query_method_3_SHOULD_tokenized(bib_obj):
	"""
	requête tokénisée souple : valeurs mot par mot unies par " "
	
	NB: introduit la boucle interne de récup des tokens sur bib_obj.api_toks
	"""
	
	longer_tokenized_query_fragments = []
	
	for champ_api in bib_obj.api_strs:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<
		if champ_api == '_NULL_':
			
			if champ_api in bib_obj.api_toks:
				field_tok_frags = ['"'+tok+'"' for tok in bib_obj.api_toks[champ_api]]
			
				# m3 liste des fragments tokenisés
				longer_tokenized_query_fragments += field_tok_frags
		
		# on a un champ structuré <<<<<<<<<<<<<
		# cas normal
		else:
			filtered_toks = bib_obj.api_toks[champ_api]
			# cas solo
			if len(filtered_toks) == 1:
				field_tokenized_frag = champ_api+':'+filtered_toks[0]
			# cas avec parenthèses
			else:
				field_tokenized_frag = champ_api+':('+' '.join(filtered_toks)+')'
			
			# liste de tous les fragments filtrés et avec leur champs
			longer_tokenized_query_fragments.append(field_tokenized_frag)
		
		# tests après chaque boucle
		#~ print("m3", longer_tokenized_query_fragments)
	
	# méthode 3 : pas de AND, pas de guillemets + filtrage des tokens les plus courts
	# (évite match par les initiales de prénoms -- peu significatives!)
	q = " ".join(longer_tokenized_query_fragments)       ## QUERY 3
	return q


def to_query_method_4_MUST_SHOULD_tokenized(bib_obj):
	"""
	requête tokénisée souple à 2 niveaux : *
	   - valeurs mot par mot unies par " "
	   - dispatchées dans 2 listes MUST et SHOULD
	
	NB: même boucle interne que la méthode 3  => field_tokenized_frag
	    mais on remplit 2 listes
	"""
	
	m4_should_tokenized_query_fragments = []      # m4
	m4_must_tokenized_query_fragments = []        # m4
	
	for champ_api in bib_obj.api_strs:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<
		if champ_api == '_NULL_':
			
			if champ_api in bib_obj.api_toks:
				field_tok_frags = ['"'+tok+'"' for tok in bib_obj.api_toks[champ_api]]
				
				# m4 => forcément should
				m4_should_tokenized_query_fragments += field_tok_frags
		
		# on a un champ structuré <<<<<<<<<<<<<
		# cas normal
		else:
			filtered_toks = bib_obj.api_toks[champ_api]
			# cas solo
			if len(filtered_toks) == 1:
				field_tokenized_frag = champ_api+':'+filtered_toks[0]
			# cas avec parenthèses
			else:
				field_tokenized_frag = champ_api+':('+' '.join(filtered_toks)+')'
			
			# et idem en stockant expressement 2 listes: les champs "MUST" | SHOULD pour la méthode 6
			if champ_api in ['publicationDate', 'host.volume']:
				m4_must_tokenized_query_fragments.append(field_tokenized_frag)
			else:
				m4_should_tokenized_query_fragments.append(field_tokenized_frag)
		
		# tests après chaque boucle
		#~ print("m4 should", m4_should_tokenized_query_fragments)
		#~ print("m4 must", m4_must_tokenized_query_fragments)
	
	# méthode 4 comme 3 mais retour d'un petit peu de strict :
	# (la date et le volume redeviennent obligatoires)
	q = None
	# TODO : pourquoi le "+" de lucene ne fonctionne pas ?
	if len(m4_must_tokenized_query_fragments):
		q = "("+" AND ".join(m4_must_tokenized_query_fragments)+") AND ("+" ".join(m4_should_tokenized_query_fragments)+")"
	return q


def to_query_method_5_MUST_SHOULD_tokenized_interpolated(bib_obj):
	"""
	requête tokénisée souple à 3 niveaux : *
	   - valeurs mot par mot unies par " "
	   - dispatchées dans 2 listes MUST et SHOULD
	   - le champ host.title (abbréviations fréquentes) reçoit des jokers
	     et j => journal
	
	NB: même boucle interne que la méthode 3  => field_tokenized_frag
	    mais on remplit 2 listes comme en 4
	    et on modifie les tokens de host.title
	"""
	
	m5_should_tokenized_query_fragments = []      # m5
	m5_must_tokenized_query_fragments = []        # m5
	
	for champ_api in bib_obj.api_strs:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<
		if champ_api == '_NULL_':
			
			if champ_api in bib_obj.api_toks:
				field_tok_frags = ['"'+tok+'"' for tok in bib_obj.api_toks[champ_api]]
				
				# m5 => forcément should
				m5_should_tokenized_query_fragments += field_tok_frags
		
		# on a un champ structuré <<<<<<<<<<<<<
		# cas normal
		else:
			filtered_toks = bib_obj.api_toks[champ_api]
			# cas solo
			if len(filtered_toks) == 1:
				field_tokenized_frag = champ_api+':'+filtered_toks[0]
			# cas avec parenthèses
			else:
				field_tokenized_frag = champ_api+':('+' '.join(filtered_toks)+')'
			
			# et idem pour méthode 7 avec jokers dans le titre de revue
			if champ_api in ['publicationDate', 'host.volume']:
				m5_must_tokenized_query_fragments.append(field_tokenized_frag)
			elif champ_api == 'host.title' and len(filtered_toks) < 8:
				# ex: "Limnol. Oceanogr J" => "Limnol* Oceanogr* journal"
				# on repasse sur les filtered_toks pour refaire ce fragment de requête
				jokered_toks = []
				for tok in filtered_toks:
					# 'j' => 'journal'
					if match(r'j|J|\]\.?', tok):
						tok = 'journal'
					# 'limnol.' => 'limnol*'
					elif tok[-1] == '.':
						tok = tok[0:-1]+'*'
					# 'oceanogr' => 'oceanogr*'
					else:
						tok = tok+'*'
					# on reprend le token transformé
					jokered_toks.append(tok)
					
				# les tokens interpolés
				new_tokenized_frag = champ_api+':('+' '.join(jokered_toks)+')'
				
				m5_should_tokenized_query_fragments.append(new_tokenized_frag)
				
				# debug
				# print(field_tokenized_frag)
			
			else:
				m5_should_tokenized_query_fragments.append(field_tokenized_frag)
			
		# tests après chaque boucle
		#~ print("m5 should",m5_should_tokenized_query_fragments)
		#~ print("m5 must", m5_must_tokenized_query_fragments)
		
	# méthode 5 comme 4 mais il y eu l'interpolation sur host.title vue plus haut
	q = None
	if len(m5_must_tokenized_query_fragments):
		q = "("+" AND ".join(m5_must_tokenized_query_fragments)+") AND ("+" ".join(m5_should_tokenized_query_fragments)+")"
	
	return q


query_funcs = (to_query_method_0_bow, 
               to_query_method_1_AND_quoted,
               to_query_method_2_SHOULD_quoted,
               to_query_method_3_SHOULD_tokenized,
               to_query_method_4_MUST_SHOULD_tokenized,
               to_query_method_5_MUST_SHOULD_tokenized_interpolated
               )


# Rappels si on veut créer d'autres fonctions de matching
# -------
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









if __name__ == '__main__':
	# -------------------------------------
	# MAIN création d'un jeu d'évaluation
	# -------------------------------------
	
	# exemple
	# 200 docs, 6588 refbibs en sortie de bib-get
	# bibfiles = ['/home/loth/refbib/a_annoter/2015-10-06_15h30-output_bibs.dir/D9F4D9BD6AB850E676DD80D89D3FD2773585B2A1.refbibs.tei.xml']
	
	try:
		my_dir = argv[1]
	except:
		warn("veuillez indiquer un dossier de sorties de grobid en argument")
		exit(1)
	
	
	# TODO ici some_docs peut être remplacé par une 
	#      array de Docs() en provenance de Corpus()
	the_files = some_docs(my_dir)

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
			
			# ------ <verbose>
			#~ subelts = [xelt for xelt in refbib.iter()]
			#~ warn("---------> contenus de la BIB GROBIDISÉE %s <--------" % str(i+1))
			#~ for xelt in subelts:
				#~ text = text_to_query_fragment(xelt.text)
				#~ if len(text):
					#~ print("  %s: %s" % (mon_xpath(xelt),text))
			# ------ </verbose>
			
			
			# on emballe le sous-arbre XML dans un objet utile + tard
			bs_obj = BiblStruct(refbib)
			
			# ==================================================
			#          F I L T R E S    E N    A M O N T
			# ==================================================
			
			# (1)
			# Test simpliste monographie ou entrée analytiques
			if not bs_obj.an_check():
				warn("WARNING: (skip) Refbib = monographie (ne peut exister dans la base)")
				continue
			
			# (2)
			# Test longueur du titre a (l'erreur la plus courante)
			if bs_obj.super_long_tit_check():
				warn("WARNING: (skip) Refbib semble avoir un titre trop long")
				continue
			
			
			# ==================================================
			#            P R E P A     R E Q U E T E S
			# ==================================================
			#  on itère sur les chemins XML internes à la bibl
			#  => clefs de dictionnaire pour ranger
			#     les valeurs texte intéressantes --> {bs_obj.subvals}
			bs_obj.bib_subvalues()
			
			# on projette sur leur équiv API    ---> {bs_obj.api_strs}
			#    et on fait une copie tokenisée ---> {bs_obj.api_toks}
			bs_obj.prepare_query_frags()
			
			# un regard pour debug
			# ---------------------
			#~ print("SUBVALS", bs_obj.subvals,"\n")
			#~ print("API_STRS", bs_obj.api_strs,"\n")
			#~ print("API_TOKS", bs_obj.api_toks,"\n")
			#~ exit()
			
			# ==================================================
			#     C O N S T R U C T I O N    R E Q U E T E S
			# ==================================================
			
			# on va gérer:
			#  - la mise sous syntaxe lucene de notre structure champ: [valeurs]
			#  - selon plusieurs différentes méthodos qu'on veut tester et comparer
			
			# à retourner liste des requêtes construites
			# (utilisables avec api.search(q=..)
			queries_to_test = []
			
			for fun_make_q in query_funcs:
				# chaque fonction listée 
				#  - boucle sur les contenus
				#  - les ajoute dans une requête lucene
				#
				# ... mais chacune le fait d'une façon un peu différente !
				
				# appel --------------
				q = fun_make_q(bs_obj)
			
				# stockage ------------
				queries_to_test.append(q)
			
			# debug
			for i, q in enumerate(queries_to_test):
				print( "REQ %i=%s" % (i,q))
			
			# ==================================================
			#         L A N C E M E N T    R E Q U E T E S
			# ==================================================
			
			print("======================================\n",
				  "DOC %s -- BIB %s\n" % (bibfile, str(i+1)))
			
			try:
				# API requests => json hits => str -------------------------------
				
				for i, rb_query in enumerate(queries_to_test):
					if rb_query:
						mon_hit_json = get_top_match_or_None(rb_query)     ## ANSWER n° i
						rb_answer = dumps(mon_hit_json, indent = 2)
					else:
						rb_answer = "Pas de requête %i (champs nécessaires absents?)" % i
				# -----------------------------------------------------------------
				
				# Sortie listing pour évaluation humaine CLI
				
					print("------\nméthode %i\n requête:%s\n match:%s\n" % (i, rb_query, rb_answer))
			
			# TODO trop large => importer URLError ?
			#      du coup pour l'instant je mets exit()
			except Exception as e:
				warn("WARNING skip car exception: '%s'" % str(e))
				exit()


	warn("liste des fichier PDF SOURCE de l'enrichissement traité :")
	for bibfile in the_files:
		print (sub('\.refbibs\.tei\.xml','.pdf', bibfile))
	
