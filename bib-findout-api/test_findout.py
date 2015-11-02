#! /usr/bin/python3
"""
Structured bibliographic refs => structured queries => filter => link

Script "test" : prépare une batterie de requêtes de résolution 
               et montre leurs premiers résultats dans l'API

      Intérêt : trouver la meilleure requête de résolution
"""

__author__    = "Romain Loth"
__copyright__ = "Copyright 2015 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.5"
__email__     = "romain.loth@inist.fr"
__status__    = "Integration"


from lxml import etree, html
from libconsulte import api
from re import search, sub, MULTILINE, match

from re import sub, search
from re import split as resplit

from os import listdir, path
from json import dumps, dump

from random import shuffle

from sys import stderr, argv

from urllib.error import HTTPError

# ---------------------------------

# encore en mode test => juste 3 docs dans le dossier fourni
TEST = False

# "json" ou "listing"
OUT_MODE = "json"


TEI_TO_LUCENE_MAP = {
	# attention parfois peut-être series au lieu de host dans la cible ?

	'analytic/title[@level="a"]'   : 'title',
	'analytic/title[@level="a"][@type="main"]'   : 'title',
	'monogr/title[@level="m"][@type="main"]'  : 'title',  # main et type=m <=> monogr entière

	'monogr/imprint/date[@type="published"]/@when' : 'publicationDate',
	'monogr/imprint/biblScope[@unit="volume"]'     : 'host.volume',
	'monogr/imprint/biblScope[@unit="vol"]'        : 'host.volume',
	'monogr/imprint/biblScope[@unit="issue"]'      : "host.issue",
	'monogr/imprint/biblScope[@unit="page"]/@to'   : 'host.pages.last',
	'monogr/imprint/biblScope[@unit="page"]/@from' : 'host.pages.first',
	'monogr/imprint/biblScope[@unit="pp"]/@to'     : 'host.pages.last',
	'monogr/imprint/biblScope[@unit="pp"]/@from'   : 'host.pages.first',

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
	'monogr/imprint/pubPlace'    :  '__IGNORE__',    # pourrait presque exclure la bib en amont (monogr)

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
	
	no_id_counter=0

	def __init__(self, xml_element, parent_doc_id=None):
		"""
		Initialisation depuis le subtree XML lu par lxml.parse(tei_doc) puis lxml.find('biblStruct')
		"""

		# slot central: l'élément XML
		# ---------------------------
		self.xelt = xml_element
		
		# sa version string 
		# (avec auto-fermants réparés pour html5)
		self.hstr = html.tostring(xml_element).decode()
		
		# warn(self.hstr)
		
		# on garde la trace du doc source
		self.srcdoc = parent_doc_id
		
		if "{http://www.w3.org/XML/1998/namespace}id" in xml_element.attrib:
			self.indoc_id = xml_element.attrib["{http://www.w3.org/XML/1998/namespace}id"]
		else:
			BiblStruct.no_id_counter += 1
			ersatz_id = "NO_ID-%i" % BiblStruct.no_id_counter
			
			warn('WARNING: bib sans ID (->%s) dans %s' % (ersatz_id, self.srcdoc))
			self.indoc_id = ersatz_id
		
		# les infos diverses : résolution impossible, etc
		
		self.log = []


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
		bow_list = [text_to_query_fragment(txt) for txt in self.xelt.itertext() if txt is not None]

		# les 3 attributs voulus
		when = self.xelt.xpath('monogr/imprint/date/@when')
		if len(when):
			bow_list.append(text_to_query_fragment(when[0]))

		pfrom = self.xelt.xpath('monogr/imprint/biblScope[@unit="page"]/@from')
		if len(pfrom):
			bow_list.append(text_to_query_fragment(pfrom[0]))

		pto = self.xelt.xpath('monogr/imprint/biblScope[@unit="page"]/@to')
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
		             tokenisées par re.split('\W').
		             et filtrées sur longueur >= 4 sauf exceptions (volume, pages)

		Utilise record() pour mettre à jour les dict en filtrant les [] et les [""]
		"""
		# dictionnaire {k => [strs]} d'expressions relevées
		# (rangé ici par xpath via préalable subvalues())
		for bibxpath in self.subvals:
			
			# todo clarifier pourquoi parfois dans les natives on a direcement du texte dans monogr/imprint
			# debug
			#~ if bibxpath == "monogr/imprint":
				#~ warn ("DEBUG: infos directement sous imprint ? %s" % str(self.subvals))
			
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
					if key in ['host.volume', 'host.issue','host.pages.first','host.pages.last']:
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
			msg = "WARNING: filtrage des tokens courts a tout supprimé (valeurs d'origine: '%s')" % self.subvals
			warn(msg)
			self.log.append(msg)

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

			# warn("=== NB de sous-elts: %i ===" % len(self.xelt))

			for elt in self.xelt.iter():

				# === cas particuliers ===
				# (tei à texte dans attributs)
				if elt.tag == 'date':
					value=None
					if 'when' in elt.attrib:
						field = mon_xpath(elt)+'/@when'
						value = elt.attrib['when']
					else:
						msg = "WARNING: date sans @when"
						warn(msg)
						self.log.append(msg)
						if elt.text:
							value = text_to_query_fragment(elt.text)

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
			warn("WARNING: sous-élément tei: '%s' absent de la table TEI_TO_LUCENE_MAP" % xpath_selector)
			champ_api = '_CHAMP_INCONNU_'

		return champ_api


	def an_check(self):
		"""
		Cherche analytic dans les premiers descendants
		"""
		for filles in self.xelt:
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
		my_titre_a_hits = self.xelt.xpath("analytic/title[@level='a']")
		if not len(my_titre_a_hits):
			return False
		else:
			my_titre_a = my_titre_a_hits.pop()
			return ( len(my_titre_a.text) > too_many )


	def test_prepare_n_apply_qfuns(self, fun_list):
		"""
		/!\ Renvoie une liste éventuellement vide de requêtes
		    en laissant un log d'erreur si c'est le cas

		Prend un objet
		  - le teste
		  - le prépare
		  - et renvoie toutes les requêtes
		"""

		#          F I L T R E S    E N    A M O N T

		# (1)
		# Test simpliste monographie ou entrée analytiques
		if not self.an_check():
			msg = "WARNING: (skip) Refbib = monographie (ne peut exister dans la base)"
			warn(msg)
			self.log.append(msg)
			return []

		# (2)
		# Test longueur du titre a (l'erreur la plus courante)
		if self.super_long_tit_check():
			msg = "WARNING: (skip) Refbib semble avoir un titre trop long"
			warn(msg)
			self.log.append(msg)
			return []


		# si on a passé les tests on parse
		# ---------------------------------
		# les valeurs texte intéressantes --> {self.subvals}
		self.bib_subvalues()

		# même valeurs texte par champ API ---> {self.api_strs}
		# copie tokenisée    par champ API ---> {self.api_toks}
		self.prepare_query_frags()
		
		# debug
		# warn("API_STRS:%s" % self.api_strs)
		# warn("API_TOKS:%s" % self.api_strs)
		
		
		#     C O N S T R U C T I O N    R E Q U E T E S

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
			q = fun_make_q(self)

			# stockage ------------
			queries_to_test.append(q)

		# debug
		#~ for i, q in enumerate(queries_to_test):
			#~ print( "REQ %i=%s" % (i,q))

		return queries_to_test
	
	@staticmethod
	def run_queries(queries_to_test):
		"""
		lancement à l'API d'une série de requêtes lucene
		(fonctionnel: suite du précédent)

		renvoie une liste de dict :
		 [{lucn_query:"..", json_answr:"..."},
		  {lucn_query:"..", json_answr:"..."}
		  ...]
		
		n'utilise pas l'objet BiblStruct
		mais dans notre utilisation est toujours
		importée au même moment, alors je la mets là
		"""

		solved_qs = []

		try:
			# API requests => json hits => str -------------------------------

			for i, rb_query in enumerate(queries_to_test):

				save = {}

				if rb_query:
					
					warn("run_queries: %i" % i)
					# warn("Q=%s" % rb_query)
					
					save["lucn_query"] = rb_query
					## ANSWER n° i =====================================
					save["json_answr"] = get_top_match_or_None(rb_query)
					## =================================================
				else:
					save["lucn_query"] = None
					save["json_answr"] = "Pas de requête %i (champs nécessaires absents?)" % i

				solved_qs.append(save)
			# -----------------------------------------------------------------
		
		except HTTPError as e:
			warn("ERROR: skip run_queries car exception: '%s'" % str(e))
			raise
		
		return solved_qs
	
	
	def test_hit(self, an_answer):
		"""
		Après run_queries, on va tester si la notice renvoyée an_answer (json de l'API) correspond à notre bib
		
		renvoie True or False
		
		NB: actuellement aucune souplesse
		
		cf. aussi les matchs dans eval_xml_refbibs
		
		TODO: match souple OCR à importer de libtrainers
		"""
		#print(">>> AVANT COMPARAISON <<<")
		#print("S.STRS", self.api_strs)
		#print("A.STRS", an_answer)
		
		test1 = False    # date + imprint + page
		test2 = False    # date + titre + auteur[0]
		                 #                ---------
		                 #       avec split simple côté base
		                 #        pour découper prénom nom
		
		# test 1
		if (('publicationDate' in self.api_strs
		     and 'host.title' in self.api_strs
		     and 'host.volume' in self.api_strs
		     and 'host.pages.first' in self.api_strs)
		and ('publicationDate' in an_answer
		      and 'host' in an_answer
		          and 'title' in an_answer['host']
		          and 'volume' in an_answer['host']
		          and 'pages' in an_answer['host']
		             and 'first' in an_answer['host']['pages'])):
		
			test1 = (
			         (self.api_strs['publicationDate'][0] == an_answer['publicationDate'])
			         # match plus souple pour les contenus texte
			     and (text2_soft_compare(self.api_strs['host.title'][0], an_answer['host']['title']))
			     and (self.api_strs['host.volume'][0] == an_answer['host']['volume'])
			     and (self.api_strs['host.pages.first'][0] == an_answer['host']['pages']['first'])
			         )
			
			# si le test1 a matché on s'arrête: c'est suffisant
			if test1:
				return True
		
		
		# si on n'a pas les infos du test1 et/ou si elles n'ont pas matché
		if (('publicationDate' in self.api_strs
		     and 'title' in self.api_strs
		     and 'author.name' in self.api_strs)
		and ('publicationDate' in an_answer
		     and 'title' in an_answer
		     and 'author' in an_answer
		          and 'name' in an_answer['author'][0])):
			
			
			# NB: les NAMES cumulent plusieurs difficultés
			# ---------------------------------------------
			# problème (1/4) >conditions<
			# dans ce test on ne compare actuellement que 
			# le premier auteur en combinaison avec titre 
			# et date
			
			# problème (2/4) >structure nom/prénom<
			# côté API noms / prénoms dans un seul champ
			# côté BIB noms / prénoms séparés
			
			# problème (3/4) >contenu prénom<
			# côté API prénoms souvent complets
			# côté BIB prénoms souvent juste initiales => ignorées
			
			# problème (4/4) >structure données<
			# chez nous BIB.api_strs: 'author.name':["AAA",...]
			# côté API                'author':{[{'name':"AAA"},...]}
			# donc accesseurs un peu différents:
			#   bib_premier_auteur = self.api_strs['author.name'][0]
			#   api_premier_auteur = an_answer['author'][0]['name']
			our_author_0 = self.api_strs['author.name'][0]
			api_author_0 = an_answer['author'][0]['name']
			
			# on va travailler sur le dernier mot-forme, en espérant que c'est le nom de famille
			# marchera souvent mais pas à tous les coup (contre-ex: "Jeanne M. Brett, MSci")
			# mais difficile de faire mieux
			api_author_0_last_token = api_author_0.split(" ")[-1]
			
			test2 = (
			         (text2_soft_compare(self.api_strs['title'][0],an_answer['title']))
			     and (self.api_strs['publicationDate'][0] == an_answer['publicationDate'])
			     and (text2_soft_compare(our_author_0,api_author_0_last_token))
			         )
			
			# debug valeurs comparées
			#~ print ('self tested:TITLE', self.api_strs['title'][0])
			#~ print ('anws tested:TITLE', an_answer['title'])
			#~ print ('self tested:DATE', self.api_strs['publicationDate'][0])
			#~ print ('answ tested:DATE', an_answer['publicationDate'])
			#~ print ('self tested:AUTH[0]', self.api_strs['author.name'][0])
			#~ print ('answ prepa:AUTH[0].split', an_answer['author'][0]['name'].split(" "))
			#~ print ('answ tested:AUTH[0].split[-1]', an_answer['author'][0]['name'].split(" ")[-1])
			
			
		# debug:
		#~ print ("%=================TEST2", test2)
		return test2

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


# Préparer une requête --------------------------------
#   text_to_query_fragment()
#      -> _text_remove_s
#      -> _text_api_safe
#      -> _text_basic_wildcard
def _text_remove_s(all_text):
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


def _text_basic_wildcard(any_text):
	"""
	Replaces '~' by '?' (from OCR convention to lucene query wildcard)

	# Explication
	# '~' est souvent un retour d'OCR signalant les caras incompris
	# ex: J. ams. ten. Pkys. Bl~sdell ~blishi~8 Company Tellus J. atmos. ten. Phys

	# '?' est le caractère joker qui correspond à la même idée dans le monde des requêtes lucene
	"""
	
	# le joker principal de toute OCR
	any_text = sub('~', '?', any_text)
	
	# spécifique au bibs ocr:"]" < src:"J"
	# or ']' rarement seul et peu pertinent pour lucene
	any_text = sub('\]', '?', any_text)
	
	return any_text


def _text_api_safe(any_text):
	"""
	modif liée au fait que même entre guillemets et
	échappées en %28 et %29, l'API va parfois voir
	les parenthèses comme opérateurs (selon position)
	
	pour le ':', idem
	pour le '[', idem
	pour le ']', idem
	pour le '\', idem
	pour le '-', idem
	
	NB: il est logique qu'il y ait des doublons avec _text_basic_wildcard
	      ==> _text_api_safe() doit passer sur tous les inputs 
	          alors que l'autre est facultatif
	"""
	
	# par ex "bonjour (tennessee" => "bonjour \( tennessee"
	any_text = sub(r'([():\[\]\\-])',r'\\\1', any_text)
	
	return any_text


def text_to_query_fragment(any_text):
	"""
	Nettoyage de chaîne à utiliser sur tout input
	"""
	if any_text is None:
		return ''
	else:
		# série minimale de préalables indispensables
		any_text = _text_remove_s(any_text)
		any_text = _text_api_safe(any_text)
		
		# heuristique liée à l'OCR
		any_text = _text_basic_wildcard(any_text)
		
		return any_text



# Faire une comparaison souple ------------------------
#   text2_soft_compare(xmltext,pdftext)
#      -> prépa commune: _text_common_prepa()
#         - suppression/normalisation espaces et ponctuations
#         - jonction césures,
#         - déligatures
#         - tout en min
#      -> prépa texte issu de PDF
#         - multimatch OCR (aka signature simplifiée)
# £TODO
#         - jonction accents eg o¨ => ö
#      -> match longueur ?
#         - caractères intercalés
#         - quelques caractères en plus à la fin
 
#  NB sur mes notations : 
#       _   = fonction privée
#     text  = fonction sur une chaîne
#             (renvoie la chaîne transformée)
#     text2 = fonction de comparaison de 2 chaînes
#             (renvoie un bool de match)

def text2_soft_compare(xmlstr,pdfstr, trace=False):
	"""
	Version initiale basique
	"""
	clean_xmlstr = _text_common_prepa(xmlstr)
	clean_pdfstr = _text_common_prepa(pdfstr)
	
	success = (clean_xmlstr == clean_pdfstr)
	
	if not success:
		xml_ocr_signature = _text_ocr_errors(clean_xmlstr)
		pdf_ocr_signature = _text_ocr_errors(clean_pdfstr)
		
		success = (xml_ocr_signature == pdf_ocr_signature)
		
		if success:
			print ("OCR match (experimental) XML:%s, PDF:%s" % (xml_ocr_signature, pdf_ocr_signature), file=stderr)
		
	if trace:
		return (success, clean_xmlstr, clean_pdfstr)
	else:
		return success

def _text_common_prepa(my_str):
	"""
	Préparation commune pour les matchs assouplis
	   - suppression/normalisation espaces et ponctuations
	   - jonction césures,
	   - déligatures
	   - tout en min
	"""
	# for my_str in [xmltext, pdftext]:
	# --------------
	# E S P A C E S
	# --------------
	# tous les caractères de contrôle (dont \t = \x{0009}, \n = \x{000A} et \r = \x{000D}) --> espace
	my_str = sub(r'[\u0000\u0001\u0002\u0003\u0004\u0005\u0006\u0007\u0008\u0009\u000A\u000B\u000C\u000D\u000E\u000F\u0010\u0011\u0012\u0013\u0014\u0015\u0016\u0017\u0018\u0019\u001A\u001B\u001C\u001D\u001E\u001F\u007F]', ' ', my_str)
	
	# Line separator
	my_str = sub(r'\u2028',' ', my_str)
	my_str = sub(r'\u2029',' ', my_str)
	
	# U+0092: parfois quote parfois cara de contrôle
	my_str = sub(r'\u0092', ' ', my_str)   
	
	# tous les espaces alternatifs --> espace
	my_str = sub(r'[\u00A0\u1680\u180E\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u200B\u202F\u205F\u3000\uFEFF]', ' ' , my_str)
	
	# pour finir on enlève les espaces en trop 
	# (dits "trailing spaces")
	my_str = sub(r'\s+', ' ', my_str)
	my_str = sub(r'^\s', '', my_str)
	my_str = sub(r'\s$', '', my_str)
	
	
	# ------------------------
	# P O N C T U A T I O N S
	# ------------------------
	# la plupart des tirets alternatifs --> tiret normal (dit "du 6")
	# (dans l'ordre U+002D U+2010 U+2011 U+2012 U+2013 U+2014 U+2015 U+2212 U+FE63)
	my_str = sub(r'[‐‑‒–—―−﹣]','-', my_str)

	# le macron aussi parfois comme tiret
	# (mais compatibilité avec desaccent ?)
	my_str = sub(r'\u00af','-', my_str)

	# Guillemets
	# ----------
	# la plupart des quotes simples --> ' APOSTROPHE
	my_str = sub(r"‘’‚`‛", "'", my_str) # U+2018 U+2019 U+201a U+201b
	my_str = sub(r'‹ ?',"'", my_str)    # U+2039 plus espace éventuel après
	my_str = sub(r' ?›',"'", my_str)    # U+203A plus espace éventuel avant
	
	# la plupart des quotes doubles --> " QUOTATION MARK
	my_str = sub(r'“”„‟', '"', my_str)  # U+201C U+201D U+201E U+201F
	my_str = sub(r'« ?', '"', my_str)   # U+20AB plus espace éventuel après
	my_str = sub(r' ?»', '"', my_str)   # U+20AB plus espace éventuel avant
	
	# deux quotes simples (préparées ci-dessus) => une double
	my_str = sub(r"''", '"', my_str)
	
	
	# --------------
	# C E S U R E S
	# --------------
	# NB: pré-supposent déjà: tr '\n' ' ' et normalisation des tirets
	my_str = sub(r'\s*-\s*', '', my_str)      # version radicale => plus de tiret
	# my_str = sub(r'(?<=\w)- ', '-', my_str) # version light avec tiret préservé
	
	
	# ------------------
	# L I G A T U R E S
	# ------------------
	my_str = sub(r'Ꜳ', 'AA', my_str)
	my_str = sub(r'ꜳ', 'aa', my_str)
	my_str = sub(r'Æ', 'AE', my_str)
	my_str = sub(r'æ', 'ae', my_str)
	my_str = sub(r'Ǳ', 'DZ', my_str)
	my_str = sub(r'ǲ', 'Dz', my_str)
	my_str = sub(r'ǳ', 'dz', my_str)
	my_str = sub(r'ﬃ', 'ffi', my_str)
	my_str = sub(r'ﬀ', 'ff', my_str)
	my_str = sub(r'ﬁ', 'fi', my_str)
	my_str = sub(r'ﬄ', 'ffl', my_str)
	my_str = sub(r'ﬂ', 'fl', my_str)
	my_str = sub(r'ﬅ', 'ft', my_str)
	my_str = sub(r'Ĳ', 'IJ', my_str)
	my_str = sub(r'ĳ', 'ij', my_str)
	my_str = sub(r'Ǉ', 'LJ', my_str)
	my_str = sub(r'ǉ', 'lj', my_str)
	my_str = sub(r'Ǌ', 'NJ', my_str)
	my_str = sub(r'ǌ', 'nj', my_str)
	my_str = sub(r'Œ', 'OE', my_str)
	my_str = sub(r'œ', 'oe', my_str)
	my_str = sub(r'\u009C', 'oe', my_str)   # U+009C (cara contrôle vu comme oe)
	my_str = sub(r'ﬆ', 'st', my_str)
	my_str = sub(r'Ꜩ', 'Tz', my_str)
	my_str = sub(r'ꜩ', 'tz', my_str)
	
	
	# --------------------
	# M I N U S C U L E S
	# --------------------
	my_str = my_str.lower()
	
	return my_str


def _text_ocr_errors(my_str):
	"""
	On oblitère les variantes graphiques
	connues pour être des paires d'erreurs
	OCR fréquentes ==> permet de comparer
	ensuite les chaînes ainsi appauvires.
	"""
	# c'est visuel... on écrase le niveau de détail des cara 
	
	# attention à ne pas trop écraser tout de même !
	# par exemple G0=Munier  T0=Muller doivent rester différents
	
	
	# ex: y|v -> v
	my_str = sub(r'nn|rn', 'm', my_str)    # /!\ 'nn' à traiter avant 'n'
	my_str = sub(r'ü|ti|fi', 'ii', my_str) # /!\ '*i' à traiter avant 'i'
	
	my_str = sub(r'O|o|ø|C\)','0', my_str)
	my_str = sub(r'1|I|l|i', '1', my_str)
	my_str = sub(r'f|t|e', 'c', my_str)    # f|c|e ?
	my_str = sub(r'y', 'v', my_str)
	my_str = sub(r'S', '5', my_str)
	#~ my_str = sub(r'c', 'e', my_str)
	my_str = sub(r'E', 'B', my_str)
	my_str = sub(r'R', 'K', my_str)
	my_str = sub(r'n|u', 'a', my_str)
	my_str = sub(r'\]', 'J', my_str)
	
	# diacritiques et cara "spéciaux"
	my_str = sub(r'\[3', 'β', my_str)
	my_str = sub(r'é|ö', '6', my_str)
	
	my_str = sub(r'ç', 'q', my_str)
	
	return my_str


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
	"""
	try:
		my_matches = api.search(
				solving_query,
				limit=1,
				outfields=['id',
					'title',
					'host.title',
					'host.volume',
					'host.pages.first',
					'host.pages.last',
					'publicationDate',
					'author.name',
					'corpusName',
					'doi'
					]
				)
	
	# peut arriver si la requête lucene est incorrecte mais ne devrait pas
	# si ça arrive => run_queries devrait faire un log dans message
	#              => un développeur devrait rajouter une règle 
	#                 dans text_to_query_fragment() ou dans 
	#                 libconsulte.api.my_url_quoting()
	except HTTPError:
		raise
		
		
	if len(my_matches):
		# json object as dict
		return my_matches[0]
	else:
		return None


def some_docs(a_dir_path, test_mode=False):
	"""
	Simple liste de documents depuis fs
	(si test, on n'en prend que 3)
	"""
	try:
		bibfiles = [path.join(a_dir_path,fi) for fi in listdir(a_dir_path)]
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

	for champ_api in bib_obj.api_toks:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<   # todo isoler avant la boucle
		if champ_api == '_NULL_':

			field_tok_frags = [tok for tok in bib_obj.api_toks['_NULL_']]

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

	for champ_api in bib_obj.api_toks:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<   # todo isoler avant la boucle
		if champ_api == '_NULL_':

			field_tok_frags = [tok for tok in bib_obj.api_toks['_NULL_']]

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

	for champ_api in bib_obj.api_toks:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<   # todo isoler avant la boucle
		if champ_api == '_NULL_':

			field_tok_frags = [tok for tok in bib_obj.api_toks['_NULL_']]

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


def to_query_method_6_MUST_tokenized(bib_obj):
	"""
	requête tokénisée stricte valeurs mot par mot unies par " "
	   - comme la méthode 3 mais avec des AND
	     (seule la dernière ligne diffère)
	"""

	longer_tokenized_query_fragments = []

	for champ_api in bib_obj.api_toks:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<   # todo isoler avant la boucle
		if champ_api == '_NULL_':

			field_tok_frags = [tok for tok in bib_obj.api_toks['_NULL_']]

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
		#~ print("m6", longer_tokenized_query_fragments)

	# méthode 6 : AND, pas de guillemets + filtrage des tokens les plus courts
	q = None
	q = " AND ".join(longer_tokenized_query_fragments)       ## QUERY 3
	return q

def to_query_method_7_MUST_tokenized_interpolated(bib_obj):
	"""
	requête tokénisée stricte valeurs mot par mot unies par " "
	   - comme la méthode 3 mais avec des AND
	
	mais avec interpolation
	   - le champ host.title (abbréviations fréquentes) reçoit des jokers
	     et j => journal
	"""

	longer_tokenized_query_fragments = []

	for champ_api in bib_obj.api_toks:
		# warn("CHAMP => REQUETE:", champ_api)
		# cas non-structuré <<<<<<<<<<<<<<<<<<   # todo isoler avant la boucle
		if champ_api == '_NULL_':

			field_tok_frags = [tok for tok in bib_obj.api_toks['_NULL_']]

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

			# et idem pour méthode 7 avec jokers dans le titre de revue
			if champ_api == 'host.title' and len(filtered_toks) < 8:
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

				longer_tokenized_query_fragments.append(new_tokenized_frag)

				# debug
				# print(field_tokenized_frag)

			else:
				longer_tokenized_query_fragments.append(field_tokenized_frag)

		# tests après chaque boucle
		#~ print("m5 should",m5_should_tokenized_query_fragments)
		#~ print("m5 must", m5_must_tokenized_query_fragments)

	q = None
	# méthode 7 : AND, pas de guillemets + filtrage des tokens les plus courts
	#             comme la 6 mais il y eu host.title avec jokers
	q = " AND ".join(longer_tokenized_query_fragments)       ## QUERY 7
	return q

query_funcs = (to_query_method_0_bow,
               to_query_method_1_AND_quoted,
               to_query_method_2_SHOULD_quoted,
               to_query_method_3_SHOULD_tokenized,
               to_query_method_4_MUST_SHOULD_tokenized,
               to_query_method_5_MUST_SHOULD_tokenized_interpolated,
               to_query_method_6_MUST_tokenized,
               to_query_method_7_MUST_tokenized_interpolated
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
#  amont
#  - longueur du titre
#  - caractères interdits dans le nom/prénom
#  - nombre de nom/prénoms
#  aval:
#    cf. t1 et t2 dans biblStruct:test_hit

# (4)
#  publicationDate:1992 => (*Date:1992 OR host.*Date:1992) ? voire range [91-93] ???



class TeiDoc(object):
	"""
	Classe hyper simple
	  (fournit les bibs en lxml.element)

	  init = lecture > parse xml
	"""
	def __init__(self, file_path):
		self.path=file_path
		
		try:
			tei_dom = etree.parse(file_path)
			
			# et voilà
			self.xtree = tei_dom
			
		except etree.XMLSyntaxError as se:
			self.xerr = str(se)
			self.xtree = None


	def get_bibs(self):
		# match conforme
		bib_elts = self.xtree.xpath('/TEI/text/back//listBibl/biblStruct')
		nb = len(bib_elts)
		
		# on tente aussi un match plus large
		bib_elts_wide = self.xtree.xpath('/TEI/text/back//biblStruct')
		
		nb_wide = len(bib_elts_wide)
		
		if nb == 0 and nb_wide == 0:
			warn("-- DOC %s: aucune bib --" % self.path)
			return []
		else:
			if nb == 0 and nb_wide != 0:
				warn("WARNING: des bibs apparaissent sans leur listBibl dans le back du doc %s" % self.path)
				
				# mais on les prend quand même
				warn("-- DOC %s: %i xbibs lues --" % (self.path,nb_wide))
				return bib_elts_wide
			
			# cas normal
			else:
				warn("-- DOC %s: %i xbibs lues --" % (self.path,nb))
				return bib_elts


	def get_iid(self):
		"""
		NB: fonction spécifique au contexte bib-findout
		
		(sinon utiliser libconsulte.Corpus.fileid)
		"""
		fname = path.basename(self.path)
		
		# ex: 0111635BF097A3A1BE4C7112F4DA0606087373A0
		m = search(r'[0-9A-F]{40}',fname)
		if m is None:
			raise TypeError("doc '%s' sans id istex" % fname)
		else:
			return m.group()



if __name__ == '__main__':
	# -------------------------------------
	# MAIN création d'un jeu d'évaluation
	# -------------------------------------

	# exemple
	# 200 docs, 6588 refbibs en sortie de bib-get
	
	try:
		my_dir_in = argv[1]
		my_dir_out = argv[2]
	except:
		warn("veuillez indiquer: \n INPUT un dossier de sorties de grobid en argument1 \n OUTPUT un dossier pour les recettes de test")
		exit(1)

	# TODO ici some_docs peut être remplacé par une
	#      array de Docs() en provenance de Corpus()
	
	# mode test: juste 3 docs /!\
	the_files = some_docs(my_dir_in, test_mode=TEST)
	
	NB_docs = len(the_files)
	
	# lecture pour chaque doc => pour chaque bib
	for d_i, bibfile in enumerate(the_files):
		
		# stockage à la fin si OUT_MODE = json
		bibinfos = []

		warn("======================================\nDOC #%i:%s" % (d_i+1,bibfile))

		teidoc = TeiDoc(bibfile)
		
		if teidoc.xtree is None:
			warn ('ERROR: (skip doc) erreur XML [%s] dans l\'input "%s"' % (teidoc.xerr, bibfile))
			continue
		
		
		bib_elts = teidoc.get_bibs()
		
		# £debug juste 10 bibs /!\
		# bib_elts = bib_elts[0:10]
		
		
		NB_bibs = len(bib_elts)
		for b_i, refbib in enumerate(bib_elts):

			# ------ <verbose>
			subelts = [xelt for xelt in refbib.iter()]
			warn("---------> contenus de la BIB GROBIDISÉE %s <--------" % str(b_i+1))
			for xelt in subelts:
				text = text_to_query_fragment(xelt.text)
				if len(text):
					print("  %s: %s" % (mon_xpath(xelt),text))
			# ------ </verbose>

			# ==================================================
			#            P R E P A     R E Q U E T E S
			# ==================================================

			# on emballe le sous-arbre XML dans un objet utile + tard
			bs_obj = BiblStruct(
			               refbib, 
			                   parent_doc_id = teidoc.get_iid())

			# là on applique ttes les fonctions passées dans la liste
			# chaque func prend l'obj bib et renvoie une q lucene (str)
			#                     --------   -------------
			queries_to_test = bs_obj.test_prepare_n_apply_qfuns(fun_list=query_funcs)
			
			# debug juste 3 requêtes
			# queries_to_test = queries_to_test[0:3]
			
			
			# ==================================================
			#         L A N C E M E N T    R E Q U E T E S
			# ==================================================

			if OUT_MODE == "listing":
				print("======================================\n",
					  "DOC %i/%i -- BIB %i/%i\n" % (d_i+1,NB_docs, b_i+1, NB_bibs))
			else:
				warn("DOC %i/%i -- BIB %i/%i\n" % (d_i+1,NB_docs, b_i+1, NB_bibs))
			
			
			# liste de dict [{lucn_query:"..", json_answr:"..."},...]
			try:
				solved_qs = bs_obj.run_queries(queries_to_test)
			except HTTPError as e:
				msg = "ERROR: skip run_queries: '%s'" % str(e)
				warn(msg)
				bs_obj.log.append(msg)
				
				# on respecte tout de même la structure attendue en sortie, mais avec None partout
				solved_qs = [{"lucn_query": rb_q, "json_answr": None} for rb_q in queries_to_test]
			
			
			# validation a posteriori : 
			#     - le hit remplit-il des contraintes de base ?
			#     - mais TODO comparaison floue :  
			#            - "Titanium :/ a panorama" != "Titanium : a panorama"  (scories PAO)
			#            - "2015-09-01"   != "2015"                             (formats transposables)
			#            - "Herman Litko" != "Herrnan Litko"                    (OCR)
			#            - "J. Limnol" != "Journal of Limnology"                (ontologie des revues)
			#            - etc.
			for qa in solved_qs:
				if qa['json_answr']:
					# on rattache une marque bool
					qa['match_flag'] =  bs_obj.test_hit(qa['json_answr'])
				else:
					qa['match_flag'] = False
			
			# debug
			# print(qa)
			
			
			if OUT_MODE == "listing":
				# Sortie listing pour lecture CLI
				for qa_i, rb_solve in enumerate(solved_qs):
					q = rb_solve['lucn_query']
					a = dumps(rb_solve['json_answr'], indent=1)
					print("------\nméthode %i\n Q:%s\n match:%s\n" % (qa_i, q, a))
			elif OUT_MODE == "json":
				# sortie d'une recette json pour affichage questionnaire web
				bibinfos.append(
				  {
				   'parent_doc'  : bs_obj.srcdoc,
				   'bib_id'      : bs_obj.indoc_id,
				   'bib_html'    : bs_obj.hstr,
				   'solved_qs'   : solved_qs,    # contient chaque q et chaque a
				   'findout_errs': bs_obj.log
				   }
				)
	
		if OUT_MODE == "json":
			doc_id = teidoc.get_iid()
			
			# bibinfos entier pour ce doc
			#   - en json
			#   - dans un fichier OUT_DIR/ID.test_resolution.json
			
			out_doc = open(my_dir_out+'/'+doc_id+'.test_resolution.json', 'w')
			dump(bibinfos, out_doc, indent=2, sort_keys=True)


	#~ warn("liste des fichier PDF SOURCE de l'enrichissement traité :")
	#~ for bibfile in the_files:
		#~ warn (sub('output_bibs.d','corpusdirs/data/A-pdfs', sub('\.refbibs\.tei\.xml','.pdf', bibfile)))
