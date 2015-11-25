#! /usr/bin/python3
"""
Structured bibliographic refs => structured query => filter => link

Script de résolution en interne:

pour chaque doc:
  pour chaque bib extraite:
    - filtrage amont (exclusion monographies et malformées)
    - transposition des champs XML en équivalents API
    - création d'une requête de résolution structurée
    - récup de son premier résultat dans l'API
    - validation ou non de ce résultat
    - ajout comme lien TEI
  sortie TEI
sortie teiCorpus
"""

__author__    = "Romain Loth"
__copyright__ = "Copyright 2015 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Development"


from lxml import etree, html
from libconsulte import api
from sys import stderr, argv
from re import search, sub, MULTILINE, match
from re import split as resplit
from urllib.error import HTTPError
from os import listdir, path

# pour some_docs uniquement
from random import shuffle

#OUT_MODE = "tab"
#OUT_MODE = "json"
OUT_MODE = "tei_xml"

DEBUG = True

TEI_TO_LUCENE_MAP = {
	# attention parfois peut-être series au lieu de host dans la cible ?

	'analytic/title[@level="a"]'   : 'title',
	'analytic/title[@level="a"][@type="main"]'   : 'title',
	'monogr/title[@level="m"][@type="main"]'  : 'title',  # main et type=m <=> monogr entière

	'monogr/imprint/date[@type="published"]/@when' : 'publicationDate',
	'monogr/imprint/date'                          : 'publicationDate',
	'monogr/imprint/date[@type="year"]'             : 'publicationDate',
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


# chargement du fichier etc/issn_abrevs.tsv
# ------------------------------------------
# format des infos lues
# { 
#   "j mol biol" :              "0022-2836",
#   "aorn j":                   "0001-2092",
#   "acta anaesthesiol scand" : "0001-5172", 
#     ...
#   (4000+ entrées)
#  }
ABREVS_REVUES = {}
install_dir = path.dirname(path.realpath(__file__))
fic_abr = open(path.join(install_dir,'etc','issn_abrevs.tsv'), 'r')
for i, line in enumerate(fic_abr):
	if match(r'[0-9]{4}-[0-9Xx]{4}\t[\w ]+$', line):
		[issn,abreviation] = line.strip().split("\t")
		ABREVS_REVUES[abreviation] = issn
	else:
		warn("(skip 1 abrev) ligne %i malformée dans etc/issn_abrevs.tsv" % i)
fic_abr.close()


class TeiDoc(object):
	"""
	Classe hyper simple pour un doc TEI parsé
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
		self.tei_subvals = None

		# cf. bib_subvalues()


		# copie des même chaînes rangées par équiv. api
		#    et idem en tokenisant
		self.api_strs = None
		self.api_toks = None

		# cf. prepare_query_frags()


		# exemples:
		# ----------
		# DONNEES SOURCES
		# self.tei_subvals {
		#  'analytic/title[@level="a"][@type="main"]'        : ['Silent myocardial ischemia'],
		#  'analytic/author/persName/surname'                : ['Cohn','Dupont'],
		#  'analytic/author/persName/forename[@type="first"]': ['Pf','F']
		#  'monogr/title[@level="j"]'                        : ['Ann Intern Med'],
		#  'monogr/imprint/date[@type="published"]/@when'    : ['1988'],
		#  'monogr/imprint/biblScope[@unit="volume"]'        : ['109'],
		#  'monogr/imprint/biblScope[@unit="page"]/@from'    : ['312'],
		#  'monogr/imprint/biblScope[@unit="page"]/@to'      : ['317'],
		#  }
		
		# POUR COMPARAISONS STRICTES A POSTERIORI
		# self.api_strs {
		#  'title'          : ['Silent myocardial ischemia'],
		#  'author.name'    : ['Cohn','Dupont'],
		#  'host.title'     : ['Ann Intern Med'],
		#  'publicationDate': ['1988'],
		#  'host.volume'    : ['109'],
		#  'host.page.first': ['312']
		#  'host.page.last' : ['317'],
		#  }
		
		# POUR REQUETES SOUPLES
		# self.api_toks {
		#  'title'          : ['Silent', 'myocardial', 'ischemia'],
		#  'author.name'    : ['Cohn', 'Dupont'],
		#  'host.title'     : ['Ann', 'Intern', 'Med'],
		#  'publicationDate': ['1988'],
		#  'host.volume'    : ['109'],
		#  'host.page.first': ['312']
		#  'host.page.last' : ['317'],
		# }



	def prepare_query_frags(self):
		"""
		Construit self.api_strs et self.api_toks
		   (permettent d'utiliser les infos structurées
		    de l'elt XML dans une query API type Lucene)

		api_strs --- re-dispatch d'un dict de str[] provenant du XML
		             vers un dict de str[] rangé par champs API
		             (permet les comparaisons strictes avec un hit API)

		api_toks --- même structure mais avec les chaînes de cara
		             tokenisées par re.split('\W').
		             et filtrées sur longueur >= 4 sauf exceptions (volume, pages)
		             (permet des requêtes efficaces dans l'API)

		On utilise record() pour mettre à jour les dict en filtrant les [] et les [""]
		"""
		
		# pour la forme tokénisée on comptera les tokens retenus
		total_kept = 0
		
		# dictionnaire {k => [strs]} d'expressions relevées
		# (rangé ici par xpath via préalable subvalues())
		for bibxpath in self.tei_subvals:
			
			# todo clarifier pourquoi parfois dans les natives on a direcement du texte dans monogr/imprint
			# debug
			#~ if bibxpath == "monogr/imprint":
				#~ warn ("DEBUG: infos directement sous imprint ? %s" % str(self.tei_subvals))
			
			# traduction des clés  TEI => API
			# --------------------------------
			# ex: monogr/author/surname => host.author.name
			champ = self.xpath_to_api_field(bibxpath)
			

			# un même point source peut avoir plusieurs chaînes
			# (notamment les noms d'auteurs) donc on a une mini boucle
			for whole_str in self.tei_subvals[bibxpath]:

				# on ignore certaines valeurs (ex: les initiales de prénoms)
				if champ == '__IGNORE__':
					continue

				# on stocke chaque chaîne avec cette nouvelle clé
				else:
					# 1 - sous forme intacte
					#     ------------------
					self.api_strs = self.record(self.api_strs, champ, whole_str)
					
					
					# 2 - sous forme tokénisée
					#     --------------------
					# from re import split as resplit
					#     on utilise [^\w?*] au lieu de \W parce qu'on ne
					#     veut pas couper sur les jokers lucene
					#     cf. text_to_query_fragment dans bib_subvalues qui
					#         a le droit d'ajouter des '?' et '*'
					for tok in resplit(r'[^\w?*]', whole_str):
						# warn("TOK %s" % tok)

						# champs ayant le droit d'être courts
						if champ in ['host.volume', 'host.issue','host.pages.first','host.pages.last']:
							
							# si API demande des valeurs numériques -------->8----
							# ----------------------------------------------------
							# on doit intercepter les cas rares non numériques
							# ex: cas volumes = "12 B" ou issue = "suppl 1"
							if search(r'[^0-9]', tok):
								
								# la partie num la plus longue
								grep_partie_num = search(r'([0-9]+)', tok)
								if grep_partie_num is not None:
									tok = grep_partie_num.groups()[0]
								else:
									# s'il n'y a rien de numérique on skip ce token
									continue
							# ----------------------------------------------------
							# ---------------------------------------------->8----
							
							# en tout cas enregistrement même si le token est court
							self.api_toks = self.record(self.api_toks, champ, tok)
							total_kept += 1

						# champs ayant le droit à des tokens plus courts
						elif champ in ['host.title', 'author.name'] and (len(tok) >= 2 or tok in ['j','J',']']):
							self.api_toks = self.record(self.api_toks, champ, tok)
							total_kept += 1

						# autres champs: tokens suffisemment longs uniquement
						elif len(tok) >= 4:
							self.api_toks = self.record(self.api_toks, champ, tok)
							total_kept += 1
			
			
		# à la fin de chaque bib on vérifie si on a bien des tokens
		if total_kept == 0:
			msg = "WARNING: filtrage des tokens courts a tout supprimé (valeurs d'origine: '%s')" % self.tei_subvals
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

		if not self.tei_subvals:

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
							field = mon_xpath(elt)
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
					if elt.text and not match(r"^\W*$", elt.text):
						field = mon_xpath(elt)
						# conversion str => str plus safe pour l'API
						str_value = text_to_query_fragment(elt.text)
						# enregistrement
						xml_subtexts_by_field = self.record(xml_subtexts_by_field, field, str_value)

			# memoize
			self.tei_subvals = xml_subtexts_by_field

		return self.tei_subvals


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
	
	
	def test_hit(self, an_answer):
		"""
		Après run_queries, on va tester si la notice renvoyée an_answer (json de l'API) correspond à notre bib
		
		renvoie True or False
		
		NB: actuellement aucune souplesse
		
		cf. aussi les matchs dans eval_xml_refbibs
		
		TODO: match souple OCR à importer de libtrainers
		"""
		#warn(">>> AVANT COMPARAISON <<<")
		#warn("S.STRS", self.api_strs)
		#warn("A.STRS", an_answer)
		
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
		          and 'issn' in an_answer['host']
		          and 'volume' in an_answer['host']
		          and 'pages' in an_answer['host']
		             and 'first' in an_answer['host']['pages'])):
			
			# variante la plus fréquente : avec titre abrégé => table <=> ISSN API
			# ex: "J. Mol. Biol." dans l'extraction
			
			j_extract = self.api_strs['host.title'][0]
			journal_key = sub("\W+", " ", j_extract.lower())
			
			# on a extrait une revue qu'on connait
			if journal_key in ABREVS_REVUES:
				
				# issn déduit du fragment extrait
				issn_revue = ABREVS_REVUES[journal_key]
				
				warn("--------> HELLO %s" % journal_key)
				warn("--------> HELLO issn_local %s" % issn_revue)
				warn("--------> HELLO issn_api %s" % an_answer['host']['issn'][0])
				
				# on vérifie le volume et les pages
				test1a = (
				         (self.api_strs['publicationDate'][0] == an_answer['publicationDate'])
				     and (issn_revue == an_answer['host']['issn'][0])
				     and (self.api_strs['host.volume'][0] == an_answer['host']['volume'])
				     and (self.api_strs['host.pages.first'][0] == an_answer['host']['pages']['first'])
				         )
			
				# si le test1a a matché on s'arrête: c'est suffisant
				if test1a:
					warn("JOURNAL MATCH: %s <=> %s <=> %s" % (journal_key, issn_revue, an_answer['host']['title']))
					return True
			
			# version avec titre entier
			if 'title' in an_answer['host']:
				test1b = (
				         (self.api_strs['publicationDate'][0] == an_answer['publicationDate'])
				         # match plus souple pour les contenus texte
				     and (soft_compare(self.api_strs['host.title'][0], an_answer['host']['title']))
				     and (self.api_strs['host.volume'][0] == an_answer['host']['volume'])
				     and (self.api_strs['host.pages.first'][0] == an_answer['host']['pages']['first'])
				         )
			
				# si le test1b a matché c'est suffisant
				if test1b:
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
			         (soft_compare(self.api_strs['title'][0],an_answer['title']))
			     and (self.api_strs['publicationDate'][0] == an_answer['publicationDate'])
			     and (soft_compare(our_author_0,api_author_0_last_token))
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

	def make_structured_query(self):
		"""
		requête tokénisée souple
		
		Elle doit être la plus large possible (s'occupe du *rappel* grâce aux atouts d'ES).
		Elle sera ensuite validée ou non par la routine test_hit (qui gèrera la précision).

		Elle utilise comme contenus les tokens de self.api_toks.
		
		Méthode de création de la requête: 
		  - champs API issus du mapping TEI_TO_LUCENE
		  - pas de AND
		  - pas de guillemets
		  - filtrage des tokens les plus courts hérité de api_toks
		  - expansion sur le nom de revue Adv => Adv*
		
		(méthode dite "méthode 3" durant les tests)
		"""

		# liste des fragments tokenisés
		longer_tokenized_query_fragments = []
		
		# 1) les éléments non-structurés d'abord (pas d'info "champ")
		if '_NULL_' in self.api_toks:
			longer_tokenized_query_fragments += [tok for tok in self.api_toks['_NULL_']]
		
		
		# 2) puis les éléments champ:valeur
		for champ_api in self.api_toks:
			# warn("CHAMP => ", champ_api)
			if champ_api != "_NULL_":
				filtered_toks = self.api_toks[champ_api]
				
				
				# -------------------------8<------------------------------------------
				# petit préalable particulier pour revue => filtered_toks
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
						# on reprend le token avec expansion
						jokered_toks.append(tok)

					# ces tokens transformés remplacent les originaux
					filtered_toks = jokered_toks
				# -------------------------8<------------------------------------------
				
				
				# ---------
				# pour tous 
				# ---------
				# cas token solo => on écrit champ:valeur
				if len(filtered_toks) == 1:
					field_tokenized_frag = champ_api+':'+filtered_toks[0]
				
				# cas plusieurs => on écrit champ:(valeur1 valeur2 etc)
				else:
					field_tokenized_frag = champ_api+':('+' '.join(filtered_toks)+')'

				# liste de tous les fragments filtrés et avec leur champs
				longer_tokenized_query_fragments.append(field_tokenized_frag)

			# tests après chaque boucle
			# print(longer_tokenized_query_fragments)

		## QUERY
		q = " ".join(longer_tokenized_query_fragments)
		
		return q



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
#   soft_compare(xmltext,pdftext)
#      -> prépa commune: _text_common_prepa()
#         - suppression/normalisation espaces et ponctuations
#         - jonction césures,
#         - déligatures
#      -> tout en min (à part pour ne pas gêner le suivant)
#      -> prépa texte issu de PDF
#         - multimatch OCR (aka signature simplifiée)
# £TODO comme dans eval_xml_refbibs.pl
#         - jonction accents eg o¨ => ö
#      -> match longueur ?
#         - caractères intercalés
#         - quelques caractères en plus à la fin
 
def soft_compare(xmlstr,pdfstr, trace=False):
	"""
	Version initiale basique
	"""
	
	if DEBUG:
		print ("|soft_compare \n|xmlstring:'%s' <=> pdfstring:'%s'" % (xmlstr, pdfstr), file=stderr)
	
	
	# 1a) dans tous les cas il faut :
	#    - supprimer les espaces en trop etc
	#    - normaliser les tirets
	#    - normaliser les quotes ?
	clean_xmlstr = _text_common_prepa(xmlstr)
	clean_pdfstr = _text_common_prepa(pdfstr)
	
	# 1b pour une première comparaison:
	#  -> minuscules
	#  -> suppression tirets
	comparable_xmlstr = sub(r'-', '', clean_xmlstr).lower()
	comparable_pdfstr = sub(r'-', '', clean_pdfstr).lower()
	
	success = (comparable_xmlstr == comparable_pdfstr)
	
	if success and DEBUG:
		print ("|soft_compare ok \n|comparable_xmlstr:'%s' <=> comparable_pdfstr:'%s'" % (comparable_xmlstr, comparable_pdfstr), file=stderr)
	
	
	# 2a) pour comparer en émulant les erreurs OCR
	#   on repart de la version sans le "tout lowercase"
	if not success and len(clean_xmlstr) > 5 and len(clean_pdfstr) > 5:
		if DEBUG:
			warn("|essai match OCR====")
		
		# on appauvrit les chaînes (eg 1|l|I ==> I)
		xml_ocr_signature = _text_ocr_errors(clean_xmlstr)
		pdf_ocr_signature = _text_ocr_errors(clean_pdfstr)
		
		# 2b) on refait après coup les faciliteurs de comparaison
		#  -> minuscules
		#  -> suppression tirets
		comparable_xml_ocr_signature = sub(r'-', '', xml_ocr_signature).lower()
		comparable_pdf_ocr_signature = sub(r'-', '', pdf_ocr_signature).lower()
	
		success = (comparable_xml_ocr_signature == comparable_pdf_ocr_signature)
		
		if DEBUG:
			print ("|OCR match (experimental) XML:%s, PDF:%s" % (comparable_xml_ocr_signature, comparable_pdf_ocr_signature), file=stderr)
	
	# Retour du résultat final de comparaison
	warn("|success: %s" % success)
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
	# NB: pré-suppose déjà: tr '\n' ' ' et normalisation des tirets
	my_str = sub(r'(?<=\w)- ', '-', my_str) # version light avec tiret préservé
	
	
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
	
	
	return my_str


def _text_ocr_errors(my_str):
	"""
	On oblitère les variantes graphiques
	connues pour être des paires d'erreurs
	OCR fréquentes ==> permet de comparer
	ensuite les chaînes ainsi appauvires.
	
	par ex: Circular fluid energy mill
	    et  Circular fluid energy rni11  <= avec 3 erreurs
	  deviennent tous les deux quelque chose comme:
	     "eIreaIar fIaId energv mIII"
	
	# (la différence rn <=> m est oblitérée)
	"""
	
	# un cas hyper fréquent à part où c <=> t
	my_str = sub(r'Sot\.', 'Soc\.', my_str)
	
	# caractère par caractère
	#   >> c'est visuel... on écrase le niveau de détail des cara 
	#   >> attention à ne pas trop écraser tout de même !
	#   >> par exemple G0=Munier  T0=Muller doivent rester différents
	
	# ex: y|v -> v
	my_str = sub(r'nn|rn', 'm', my_str)    # /!\ 'nn' à traiter avant 'n'
	my_str = sub(r'0|O|o|ø|C\)','0', my_str)
	my_str = sub(r'1|I|l|i|\]', 'I', my_str)
	my_str = sub(r't', 'f', my_str)         # sous-entendu r'f|t' => 'f'
	my_str = sub(r'c', 'e', my_str)         # etc. idem
	my_str = sub(r'y', 'v', my_str)
	my_str = sub(r'S', '5', my_str)
	my_str = sub(r'E', 'B', my_str)
	my_str = sub(r'R', 'K', my_str)
	my_str = sub(r'u', 'a', my_str)
	my_str = sub(r'\]|\.I', 'J', my_str)
	
	# diacritiques et cara "spéciaux"
	my_str = sub(r'\[3', 'β', my_str)
	my_str = sub(r'é|ö', '6', my_str)
	
	my_str = sub(r'ç', 'q', my_str)
	
	
	# erreurs OCR existantes mais à transfo très forte
	# ici pour mémoire mais désactivées
	# (vu la freq de ces caras c'est fortement appauvrissant)
	# my_str = sub(r'f|t|e|c', 'c', my_str)
	# my_str = sub(r'n|u|a', 'a', my_str)
	# my_str = sub(r'ü|ti|fi', 'ii', my_str) # /!\ '*i' à traiter avant 'i'
	
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
	=> input = one string (lucene query)
	=> output = one json object or None
	"""
	
	# debug
	if type(solving_query) != str:
		raise TypeError("ERROR: la requête n'est pas du texte")
	
	# on lance la requête via api.search()
	# seul le premier hit est renvoyé
	try:
		my_matches = api.search(
				solving_query,
				limit=1,
				outfields=['id',
					'title',
					'host.issn',
					'host.title',
					'host.volume',
					'host.pages.first',
					'host.pages.last',
					'publicationDate',
					'author.name',
					'corpusName',
					'doi']
				)
	
	# HTTPError peut arriver si la requête lucene est incorrecte mais ne devrait pas!
	# si ça arrive => le main attrape l'exception et signale "ERROR: (skip requête)"
	#              => un développeur devrait rajouter une règle 
	#                 dans text_to_query_fragment() ou dans 
	#                 libconsulte.api.my_url_quoting()
	#                 pour resp. supprimer ou échapper 
	#                 le caractère posant problème
	except HTTPError:
		raise
		
	
	# cas normal [un_hit_json]
	if len(my_matches):
		# json object as dict
		return my_matches[0]
	
	# cas [] => devient None pour nous
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


# -------------------------------------
#               MAIN
# -------------------------------------

if __name__ == '__main__':
	try:
		my_dir_in = argv[1]
		my_dir_out = argv[2]
	except:
		warn("veuillez indiquer: \n INPUT un dossier de sorties de grobid en argument1 \n OUTPUT un dossier pour les recettes de test")
		exit(1)

	# TODO ici some_docs peut être remplacé par une
	#      array de Docs() en provenance de Corpus()
	
	# mode test: juste 3 docs /!\
	the_files = some_docs(my_dir_in, test_mode=True)
	
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
		
		# récup par xpath
		bib_elts = teidoc.get_bibs()
		
		# £debug juste 10 bibs /!\
		# bib_elts = bib_elts[0:10]
		
		# taille de la liste à traiter
		NB_bibs = len(bib_elts)
		
		# si jamais il n'y a pas d'IDs pour les bibs
		# la classe BiblStruct les refera avec ce compteur
		BiblStruct.no_id_counter = 0
		
		
		for b_i, refbib in enumerate(bib_elts):
			
			warn("======================================\nDOC %i/%i -- BIB %i/%i\n" % (d_i+1,NB_docs, b_i+1, NB_bibs))

			# ------ <verbose>
			subelts = [xelt for xelt in refbib.iter()]
			warn("---------> contenus de la BIB GROBIDISÉE %s <--------" % str(b_i+1))
			for xelt in subelts:
				text = text_to_query_fragment(xelt.text)
				if len(text):
					warn("  %s: %s" % (mon_xpath(xelt),text))
			# ------ </verbose>
			
			
			# changera de valeur ssi on obtient un hit ET qu'il est validé
			found_id_or_none = None
			
			# ==================================================
			#            P R E P A     R E Q U E T E S
			
			# on emballe le sous-arbre XML dans un objet utile + tard
			bs_obj = BiblStruct(
			               refbib, 
			                   parent_doc_id = teidoc.get_iid())
			
			
			# F I L T R E S    E N    A M O N T
			# ----------------------------------
			# ici on va tester si c'est une bib correcte
			# puis :
			#  si oui on crée une requête lucene à partir de l'objet bib
			#         --------------------------
			#  si non on laisse un warning
		    
			# (1)
			# Test simpliste monographie ou entrée analytiques
			if not bs_obj.an_check():
				msg = "WARNING: (skip) Refbib = monographie (ne peut exister dans la base)"
				warn(msg)
				bs_obj.log.append(msg)
				the_query = None

			# (2)
			# Test longueur du titre de niveau "a" 
			# (c'est là que le CRF met tout s'il n'a rien compris ou que c'est une fausse bib)
			elif bs_obj.super_long_tit_check():
				msg = "WARNING: (skip) Refbib semble avoir un titre trop long"
				warn(msg)
				bs_obj.log.append(msg)
				the_query = None

			# cas normal
			else:
				# C O N S T R U C T I O N    R E Q U E T E
				# -----------------------------------------
				# si on a passé les tests on parse
				bs_obj.bib_subvalues()
				
				# les valeurs texte intéressantes sont à présent dans {self.tei_subvals}

				# même valeurs texte tokénisées et rangées par champ API ---> {self.api_toks}
				bs_obj.prepare_query_frags()
			
				# debug
				warn("API_STRS:%s" % bs_obj.api_strs)
				warn("API_TOKS:%s" % bs_obj.api_toks)
			
				# mise sous syntaxe lucene de notre structure champ: [valeurs]
				the_query = bs_obj.make_structured_query()
			
			
			warn("THE_QUERY:%s\n" % the_query)
			
			if the_query is not None:

				# ==================================================
				#         L A N C E M E N T    R E Q U E T E S

				# liste de dict [{lucn_query:"..", json_answr:"..."},...]
				try:
					# lancement à l'API d'une requête lucene => réponse json
					json_answr = get_top_match_or_None(the_query)
					
					# debug
					warn("JSON_ANSWR (unchecked):%s" % json_answr)
				
				except HTTPError as e:
					json_answr = None
					msg = "ERROR: (skip requête): '%s'" % str(e)
					warn(msg)
					bs_obj.log.append(msg)
			
			
				# ==================================================
				#      V A L I D A T I O N    R E P O N S E
				#
				# a posteriori on passe la routine *test_hit*
				#   - le hit remplit-il des contraintes de base ?
				#   - avec comparaison intelligente mais stricte :  
				#        - "Titanium :/ a panorama" != "Titanium : a panorama"  (scories PAO)
				#        - "2015-09-01"   <=> "2015"                             (formats transposables)                                       
				#        - "Herman Litko" <=> "Herrnan Litko"                    (OCR)
				#        - "J. Limnol" <=> "Journal of Limnology"    TODO        (ontologie des revues)
				#        - etc.
				
				if json_answr is not None:
					# revérification "intelligente" de notre côté
					if bs_obj.test_hit(json_answr):
						
						# si et seulement si le match a été validé
						found_id_or_none = json_answr['id']
						
						# pour infos
						warn("VALID ANSWER   ^^^^^^^^^^^^^^^^^^^^^^^^   VALID ANSWER")
			
			warn("MATCH: %s" % str(found_id_or_none))
			
			
			# ==================================
			#   S O R T I E S    P A R    B I B
			
			# dans tous les cas on sort un tableau résumé
			#
			# 3 cols ex:
			#   ID SOURCE |  ID BIB  |  ID RESOLUE
			# -------------------------------------
			#   49548E... |   b0     |  100E86...    <== lien trouvé
			#   49548E... |   b1     |   None        <== pas trouvé
			#        etc.
			print("\t".join([bs_obj.srcdoc,bs_obj.indoc_id,str(found_id_or_none)]))
			
			
			if OUT_MODE == "json":
				# sortie détaillée json dans un fichier
				bibinfos.append(
				  {
				   'parent_doc'  : bs_obj.srcdoc,
				   'bib_id'      : bs_obj.indoc_id,
				   'bib_html'    : bs_obj.hstr,
				   'query'       : the_query,
				   'valid_hit_id': found_id_or_none,
				   'valid_hit'   : json_answr,
				   'findout_errs': bs_obj.log
				   }
				)
			
			
			elif OUT_MODE == "tei_xml":
				if found_id_or_none is not None:
					# le nouvel élément
					new_xref = etree.Element("ref", type="istex-url")
					
					# son contenu
					new_xref.text = "https://api.istex.fr/document/" + found_id_or_none
					
					# ajout dans la DOM dans le biblStruct
					bs_obj.xelt.append(new_xref)
					
					# forme de l'élément qu'on vient d'ajouter!
					# <ref type="istex-url">https://api.istex.fr/document/$found_id</ref>
			
			# fin boucle par bib
		
		
		# ==================================
		#   S O R T I E S    P A R    D O C
		# 
		# modes XML ou JSON: écriture d'un fichier par doc source
		
		if OUT_MODE == "json":
			doc_id = teidoc.get_iid()
			
			# bibinfos entier pour ce doc
			#   - en json
			#   - dans un fichier OUT_DIR/ID.resolution.json
			
			out_doc_json = open(my_dir_out+'/'+doc_id+'.resolution.json', 'w')
			dump(bibinfos, out_doc, indent=2, sort_keys=True)
			out_doc_json.close()
		
		elif OUT_MODE == "tei_xml":
			# get_iid() à modifier éventuellement
			doc_id = teidoc.get_iid()
			out_doc_xml_path = my_dir_out+'/'+doc_id+'.tei.xml'
			
			# écriture XML enrichi
			teidoc.xtree.write(out_doc_xml_path, pretty_print=True)
			