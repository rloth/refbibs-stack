#! /usr/bin/python3

import re
import sys
from lxml import etree

from math import ceil


# quelques helper regexps
re_REF_HEADER_LINE = re.compile(r"^R ?[Ee] ?[Ff] ?[Ee] ?[Rr] ?[Ee] ?[Nn] ?[Cc] ?[Ee] ?[Ss]?s*:?\s*$")





# --------------------------------------------------------
# -A- helpers

# --------------------------------------------------------
NSMAP = {'tei': "http://www.tei-c.org/ns/1.0"}


def glance_xbib(bS, longer = False):
	"""Donne un infostr ou aperçu du contenu d'une biblio structurée XML
	
	Arguments:
		bS -- l'entrée biblio
		longer -- un booléen pour format étendu 
	"""
	# variables du glance
	# article title if present, or monog title, or nothing 
	main_title  = None
	main_author = None
	the_year  = None
	the_id    = None
	
	# id
	id_elt = bS.xpath("@xml:id")
	if len(id_elt):
		the_id = id_elt[0]
		
	# date
	date_elts = bS.xpath(".//tei:imprint/tei:date", namespaces=NSMAP)
	if len(date_elts) == 1:
		# 2 manières de noter la date: attribut when ou contenu balise
		# si attribut @when
		if "when" in date_elts[0].keys():
			the_year = date_elts[0].get("when")[0:4]
		# sinon contenu
		else:
			the_year = date_elts[0].text[0:4]
	# sinon la date reste à None
	elif len(date_elts) > 1:
		print ("plusieurs dates", file=sys.stderr)
	
	# check bool entrée analytique ??
	has_analytic  = (len(bS.xpath("tei:analytic", namespaces=NSMAP)) > 0)
	
	
	if has_analytic:
		ana_tit_elts = bS.xpath("tei:analytic/tei:title", namespaces=NSMAP)
		if len(ana_tit_elts):
			main_title = ana_tit_elts[0].text 
		
		ana_au_elts = bS.xpath("tei:analytic/tei:author//tei:surname", namespaces=NSMAP)
		if len(ana_au_elts):
			main_author = ana_au_elts[0].text
	
	# on va chercher auteur et titre dans monogr si ils manquaient dans analytic
	if (main_title is None):
		monogr_tit_elts = bS.xpath("tei:monogr/tei:title", namespaces=NSMAP)
		if len(monogr_tit_elts):
			main_title = monogr_tit_elts[0].text
		else:
			main_title = "_NA_"
	
	if (main_author == None):
		monogr_au_elts = bS.xpath("tei:monogr/tei:author//tei:surname", namespaces=NSMAP)
		if len(monogr_au_elts):
			main_author = monogr_au_elts[0].text
		else:
			main_author = "_NA_" # on ne laisse pas à None car on doit renvoyer str
	
	# NB : il peuvent éventuellement toujours être none si éléments à texte vide ?
	
	# build "short" string
	my_desc = "("+main_author[:min(5,len(main_author))]+"-"+str(the_year)+")" 
	
	# optional longer string
	#~ if longer:
		#~ maxlen = min(16,len(main_title))
		#~ my_desc = the_id+":"+my_desc+":'"+main_title[:maxlen]+"'"
	
	return my_desc

# --------------------------------------------------------




# --------------------------------------------------------
# -B- procédures principales
# <<xml_elts_to_match_tokens
# <<match_citation_fields
# link_txt_bibs_with_xml
# find_bib_zone


def link_txt_bibs_with_xml(pdfbibzone, xmlbibnodes, debug=0):
	"""Trouver quelle biblStruct correspond le mieux à ch. ligne dans zone ?
	   (~ reference-segmenter)
	TODO 
	  - on n'utilise pas assez la double séquentialité
	"""
	
	m_xnodes = len(xmlbibnodes)
	n_pzone = len(pdfbibzone)
	
	# initialisation matrice de décomptes cooc.
	scores_pl_xb = [[0 for j in range(m_xnodes)] for i in range(n_pzone)]

	# remarques sur matrice cooccurrences
	# -----------------------------------
	# en ligne: une ligne digitalisée du pdftotext
	# en colonne: une des refbibs du xml
	#  
	# (~> "similarité" entre les lignes pdf et les entrées xml)
	#
	# la matrice devrait être +- diagonale 
	# car il y a co-séquentialité des deux
	# (transcriptions d'une même source)
	#
	# exemple matrice remplie sur 6 lignes pdf et 4 noeuds xml
	# -----------------------
	# [ 10,  1,  0,  2 ] : "1 M. Morra, E. Occhiello and F. Garbassi, J . Colloid Interface Sci.,"
	# [  3,  0,  0,  0 ] : "1992, 149, 290."
	# [  1,  6,  0,  2 ] : "2 E. N. Dalal, Langmuir, 1987, 3, 1009."
	# [  1,  1,  0,  1 ] : "3 J. Domingue, Am. Lab., October, 1990, p. 5 ."
	# [  2,  1,  0, 13 ] : "4 D. J. Gardner, N. C. Generalla. D. W. Gunnells and M. P."
	# [  0,  1,  0,  5 ] : "Wolcolt, Langmuir, 1991, 7 , 2498."
	
	# la pdfligne 1 (ligne du haut) est très semblable à la 1ère xbib (score de 10)
	# et on voit que la ligne suivante est une suite de cette même xbib (score de 3)
	# (en colonne 3 on voit aussi une des xbibs toute vide)
	# ( => conversion tei en amont probablement mal passée)
	# -----------------------------------
	
	# compte des cooccurrences => remplissage matrice
	# ========================
	for i, probable_bib_line in enumerate(pdfbibzone):
		# représentation de la ligne plus pratique
		# (prépare les bouts de match effectuables avant de les compter ensemble)
		
		pdf_w_tokens =  [o for o in re.split(r'\W+', probable_bib_line) if (len(o) and o not in ["&", "and", "in", "In"])]
		# remarque : split sur "\W+" et non pas "\s+"
		# -------------------------------------------
		# la ponctuation ajoutée ne nous intéresse pas encore 
		# et pourrait gêner l'apparillage des lignes
		
		# print(pdf_w_tokens, file=sys.stderr)
		
		for j, xbib in enumerate(xmlbibnodes):
			# count count
			# décompte de cooccurrences (pl.bow <=> xb.bow)
			for ptok in pdf_w_tokens:
				if debug >= 3:
					print("match essai frag pdf du i=%i: '%s'" %(i , re.escape(ptok)), file=sys.stderr)
				
				reptok = re.compile(r"\b%s\b" % re.escape(ptok))
				
				for xtext in xbib.itertext():
					if debug >= 4:
						print("\tsur frag xml du j=%i: %s" % (j, xtext), file=sys.stderr)
					
					# MATCH !
					if reptok.search(xtext):
						if debug >= 4:
							print("\t\tMATCH (i=%i, j=%i)!" % (i,j), file=sys.stderr)
						scores_pl_xb[i][j] += 1 
						# + d'un match de même ptok sur le même xtxt n'est pas intéressant
						break
	
	# pour log
	# --------
	if debug >= 2:
		# reboucle: affichage détaillé pour log de la matrice des scores
		for i in range(len(pdfbibzone)):
			# ligne courante : [valeurs de similarité] verbatim de la ligne
			print("pdf>biblio>l.%i: %s (max:%i) txt:'%s'" % (
					  i,
					  scores_pl_xb[i], 
					  max(scores_pl_xb[i]), 
					  # correspond à rawlines[debut_zone+i]
					  pdfbibzone[i]
					 ),
				file=sys.stderr)
	
	
	# RECHERCHE champions   
	# ===================
	# [argmax_j de scores[i][j] for j in xbibs], for i in rawlines
	#
	# => à remplir ici
	champions = [None for x in range(n_pzone)]
	
	# mémoire du précédent pour favoriser ré-attributions *du même*
	mem_previous_argmax_j = None
	
	# TODO mémoire plus longue pour favoriser attributions consécutives *du suivant* [i+1] aussi
	
	for i in range(n_pzone):
		# a priori on ne sait pas
		argmax_j = None
		
		# on espère un score gagnant franc, mais peut être 0
		the_max_val = max(scores_pl_xb[i])
		
		# on n'utilise pas indexof(the_max_val) car si *ex aequo* on les veut tous
		candidats = [j for j in range(m_xnodes) if scores_pl_xb[i][j] == the_max_val]
		
		# si plusieurs ex aequo
		# ----------------------
		if len(candidats) > 1:
			
			# cas à noter: la ligne est pratiquement vide
			if the_max_val == 0:
				champions[i] = None
				if debug >= 2:
					print( "l.%i %-90s: NONE tout à 0" % (i, pdfbibzone[i]), file=sys.stderr)
			
			# cas rare: attribution raisonnable au précédent
			# ... si mem_previous_argmax_j in candidats
			#     malgré ambiguïté des similarités
			elif (mem_previous_argmax_j in candidats
			     and the_max_val > 5
			     and len(candidats) <= m_xnodes/10):
				# Explication
				# - - - - - -
				# ex: txt:'T., Furukawa, T., Yamada, K., Akiyama, S. and' 
				#     candidats exaequo bibs [7, 9, 28] à max 7
				#     et mem_previous_argmax_j = 9
				# cas ambigüs (eg auteurs aussi présents ailleurs,
				#              ou que des mots présents ailleurs)
				# mais consécutifs à une attribution claire
				#      - - - - - - - - - - - - - - - - - - -
				# => bravo REPECHAGE !
				argmax_j = mem_previous_argmax_j
				champions[i] = argmax_j
				
				# log
				if debug >= 1:
					ma_bS = xmlbibnodes[argmax_j]
					infostr = glance_xbib(ma_bS)
					print( "l.%i %-90s: WINs suite XML %s %s (max=%s) (repêchage parmi %s ex aequo)" % (
						  i,
						  pdfbibzone[i],
						  argmax_j,
						  infostr,
						  the_max_val, 
						  candidats
						 ),
						file=sys.stderr)
			# cas générique ex aequo: *match pas concluant*
			# - - - - - - - - - - - - - - - - - - - - - - -
			else:
				if debug >= 1:
					print("l.%i %-90s: NONE exaequo bibs %s (maxs=%i)"  % (
						  i,
						  pdfbibzone[i],
						  candidats, 
						  the_max_val, 
						 ),
						file=sys.stderr)
		
		# --------------------------------
		# là on a un match intéressant...
		# --------------------------------
		elif len(candidats) == 1:
			
			# on en a un !
			argmax_j = candidats.pop()
			
			# à quelles valeurs max s'attendre ?
			# -----------------------------------
			# Pour une **ligne normale** on aura en général the_max_val > 10 avec observés [6-17]
			# (citation entière ou début d'une citation sur ligne entière :
			# la valeur max est alors assez haut : bon nombre d'infos casées
			
			# Par contre pour une **ligne de continuation** il est tout 
			# à fait normal d'avoir une max_val basse, à 1 ou 2
			# (donc plus difficile à repérer)
			
			# ligne normale
			if argmax_j != mem_previous_argmax_j:
				
				# match pas folichon
				if the_max_val < 5 :
					if debug >= 2:
						print("l.%i %-90s: WEAK (max=%i) (x vide? ou cette ligne p vide ?)" % (i, pdfbibzone[i], the_max_val), file=sys.stderr)
					# oublier résultat incertain
					argmax_j = None
				
				# xml correspondant trouvé !
				else:
					# bravo !
					champions[i] = argmax_j
					
					# log
					if debug >= 1:
						ma_bS = xmlbibnodes[argmax_j]
						infostr = glance_xbib(ma_bS, longer=True)
						print( "l.%i %-90s: WIN1 entrée XML %s %s (max=%i)" % (
							  i,
							  pdfbibzone[i],
							  argmax_j,
							  infostr,
							  the_max_val
							 ),
							file=sys.stderr)
			
			# ligne de continuation potentielle (même xbib préférée que le précédent)
			else:
				# moyenne des autres
				the_drift = sum([x for j,x in enumerate(scores_pl_xb[i]) if j != argmax_j]) / m_xnodes
				
				# tout le reste est bas, on est plus haut 
				# et on trouve le même que mémorisé
				# => on va dire que c'est concluant !
				if (the_max_val > 2 * the_drift):
					# bravo !
					champions[i] = argmax_j
					
					# log
					if debug >= 2:
						ma_bS = xmlbibnodes[argmax_j]
						infostr = glance_xbib(ma_bS, longer=True)
						print( "l.%i %-90s: WINs suite XML %s %s (max=%i vs d=%f) " % (
							  i,
							  pdfbibzone[i],
							  argmax_j,
							  infostr,
							  the_max_val, 
							  the_drift
							 ),
							file=sys.stderr)
				else:
					# TODO mettre une info "__WEAK__" dans champions[i] pour diagnostics
					if debug >= 1:
						print("l.%i %-90s: WEAK (max=%i vs d=%f)" % (
							  i,
							  pdfbibzone[i],
							  the_max_val,
							  the_drift
							 ),
							file=sys.stderr)
		# wtf?
		else:
			raise ValueError("len(candidats)")
		
		# mémorisation de durée 1
		mem_previous_argmax_j = argmax_j
	
	# liste pour chaque ligne i la valeur de bib j trouvée, ou None
	return champions
	
	# exemple interprétation liste
	# ----------------------------
	# [None, 0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, None, None, None, None, 4, 5, 5, 6, 6, 7, 7]
	#                    ^^^^^^^^                ^^^^^^^^^^^^^^^^^^^^^^ 
	#                ici lignes i=[6,7,8]       probablement saut de page
	#                 matchent xbib j=2

# --------------------------------------------------------

# --------------------------------------------------------

def find_bib_zone (xmlbibnodes, rawtxtlines, debug=0):
	"""Trouve la zone de bibs dans du texte brut
	       - en utilisant les infos de la bibl structurée XML 
	         supposée dispo (ça aide beaucoup)
	       - en regardant l'aspect intrinsèque de la ligne (aide la précision du précédent)
	       - ou tout simplement si on trouve l'intitulé "References"
	"""
	# integers to be found (indices)
	debut = None
	fin = None
	
	# var remplie ssi vu l'expression /References:?/
	# => simplifie la recherche du début !
	ref_header_i0 = None
	
	# decompte de 'clues'
	# ===================
	# on mesure les occurrences dans rawlines de:
	#   - search_toks : tout fragment connu xbib
	#   - re_... : helper tokens = certaines propriétés biblio-like
	#                              (commence par majusc, label, etc)

	# n = nombre de lignes
	n_lines = len(rawtxtlines)
	
	# --------------
	# xmlelts tokens
	# --------------
	
	# tous les contenus texte des elts xml, en vrac
	xmltexts = []
	
	# remplissage xmltexts
	for j, xbib in enumerate(xmlbibnodes):
		thisbib_texts=[]
		for eltstr in xbib.itertext():
			thisbib_texts.append(eltstr)
		
		# TODO : vérifier si intéressant de les préserver séparément (liste de listes)
		xmltexts += thisbib_texts
	
	# count array for each match re.search(r'xmlelts', textline)
	tl_match_occs = []
	
	# pour décompte un pré-préalable : 
	# regex compile each token found in the xml
	search_toks = set()
	for st in xmltexts:
		for tok in re.split(r"\W+", st):
			if is_searchable(tok):
				etok = re.escape(tok)
				
				# TODO ajouter décision du format des limites 
				# gauche et droite pour les \b comme dans XTokinfo
				
				search_toks.add(re.compile(r"\b%s\b" % etok))
	
	# TODO : est-ce que les noms communs du XML content devraient être enlevés ?
	# cf. ech/tei.xml/oup_Geophysical_Journal_International_-2010_v1-v183_gji121_3_gji121_3xml_121-3-789.xml
	
	if debug >= 2:
		print (search_toks, "<== Those are the searched tokens", file=sys.stderr)
	
	
	# -------------
	# helper tokens (puncts, digits, capitalized letters)
	# -------------
	# pdc toks count array
	pdc_match_occs = []
	
	# date + ponctuation (très caractéristique des lignes refbib) : exemples "(2005)", "2005a," 
	re_datepunct = re.compile(r"[:;,.\(\[]?\s?(?:18|19|20)[0-9]{2}[abcde]?\s?[:;,.\)\]]")
	# exemples : "68(3):858-862" ou "68: 858-862" ou "68: 858"
	re_vol_infoA = re.compile(r"[0-9]+(?:\([0-9]+\))?\s?:\s?[0-9]+\s?(?:[-‒–—―−﹣]\s?[0-9]+)?")
	# exemples : "vol. 5, no. 8, pp. 1371"   "Vol. 5, No. 8, pp 1371-1372
	re_vol_infoB = re.compile(r"\b[Vv]ol\.?\s?[0-9]+\s?[,\.;]\s?[Nn]o\.?\s?[0-9]+\s?[,\.;]\s?pp?\.?\s?\d+\s?[-–]?\s?\d*")
	# exemples : "68(3), 858-862" ou "68, 858-862"
	re_vol_infoC = re.compile(r"[0-9]+(?:\([0-9]+\))?\s?,\s?[0-9]+\s?[-‒–—―−﹣]\s?[0-9]+")
	
	# reconnaissance de fragments très générique : marche uniquement car vol n'est pas un mot (l'équivalent pour "No" serait irréaliste)
	re_vol = re.compile(r"\b[Vv]ol\.?(?=[\s\d])")
	re_ppA = re.compile(r"\bpp\.?(?=[\s\d])")
	re_ppB = re.compile(r"\b[0-9]+\s?[-‒–—―−﹣]\s?[0-9]+\b")
	# plus rares mais surs (à cause de la présence du ':')
	re_in = re.compile(r"\b[Ii]n ?:")
	re_doi = re.compile(r"\bdoi: ?10\.[\S]+")
	
	# re_init <=> intéressants seulement en début de ligne -> re.match
	re_initlabel = re.compile(r"\[.{1,4}\]")
	re_initcapncap = re.compile(r"(?:\[.{1,4}\])\s*[A-Z].*?\b[A-Z]")
	
	# -------------------
	# boucle de décompte 
	# -------------------
	for i, tline in enumerate(rawtxtlines):
		# new initial counts for this line
		tl_match_occs.append(0)
		pdc_match_occs.append(0)
		
	# filter out very short text lines
		if len(tline) <= 2:
			next
		
		# - - - - - - - - - - - - - - - - - - - -
		# décompte principal sur chaque xfragment
		# - - - - - - - - - - - - - - - - - - - -
		for tok_xfrag_re in search_toks:
			# 2 points if we matched an XML content
			if re.search(tok_xfrag_re, tline):
				tl_match_occs[i] += 2
		
		# décompte indices complémentaires
		# indices forts => 2 points
		pdc_match_occs[i] += 2 * len(re.findall(re_datepunct, tline))
		pdc_match_occs[i] += 2 * len(re.findall(re_vol_infoA, tline))
		pdc_match_occs[i] += 2 * len(re.findall(re_vol_infoB, tline))
		pdc_match_occs[i] += 2 * len(re.findall(re_vol_infoC, tline))
		pdc_match_occs[i] += 2 * len(re.findall(re_in, tline))
		pdc_match_occs[i] += 3 * len(re.findall(re_doi, tline))
		
		# indices plus heuristiques => 1 points
		pdc_match_occs[i] += 1 * len(re.findall(re_vol, tline))
		pdc_match_occs[i] += 1 * len(re.findall(re_ppA, tline))
		pdc_match_occs[i] += 1 * len(re.findall(re_ppB, tline))
		
		# indices ancrés sur ^ 
		# initlabel
		if re.match(re_initlabel, tline):
			pdc_match_occs[i] += 2
		
		# initcap
		if re.match(re_initcapncap, tline):
			pdc_match_occs[i] += 2
		
		# -------------------8<-----------------------
		# au passage si on trouve le début directement
		# (ne fait pas partie des décomptes mais même boucle)
		if re.match(re_REF_HEADER_LINE, tline):
			# on reporte ça servira plus tard
			ref_header_i0 = i
		# -------------------8<-----------------------
		
		# listing d'observation détaillée
		if debug >= 2:
			print("-"*20+"\n"+"line n. "+str(i)+" : "+tline, file=sys.stderr)
			print("found %i known text fragments from XML content" %  tl_match_occs[i], file=sys.stderr)
			print("found %i typical bibl formats from helper toks" % pdc_match_occs[i] + "\n"+"-"*20, file=sys.stderr)
	
	# sum of 2 arrays
	all_occs = [(tl_match_occs[i] + pdc_match_occs[i]) for i in range(n_lines)]
	
	# log: show arrays
	if debug >= 3:
		print("tl_match_occs\n",tl_match_occs, file=sys.stderr)
		print("pdc_match_occs\n",pdc_match_occs, file=sys.stderr)
	if debug >= 2:
		print("all_match_occs\n",all_occs, file=sys.stderr)
	
		# type de résultat obtenu dans tl_match_occs (seq de totaux par ligne):
		# [0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0,
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
		#  0, 0, 0, 0, 0, 0, 5, 8, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0,
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0,
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0,
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
		#  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0,
		#  7, 3, 6, 1, 3, 10, 0, 0, 11, 8, 2, 0, 0]
		
		# !! potentiellement jusqu'à 20 fois + gros
	
	
	# -----------------------
	# Répérage proprement dit
	
	# LE DEBUT
	# ========
	
	# cas si on a déjà le début 
	# --------------------------
	if ref_header_i0 is not None:
		# la ligne après l'entête
		debut = ref_header_i0 + 1
	
	else:
		# identification début si on n'a qu'une bib
		# -----------------------------------
		if (len(xmlbibnodes) == 1):
			# cas un peu spécial : 
			# ==> on ne peut pas compter sur vérifs des lignes d'avant/après
			# ==> on prend la ligne max puis éventuellement suivante(s)
			
			argmax_i = all_occs.index(max(all_occs))
			debut = argmax_i
		
		# identification si on a plusieurs bibs
		# -----------------------------------------------
		# Décision d'après all_occs avec grand lookahead
		# -----------------------------------------------
		else:
			# all_occs => Là-dedans on cherche une zone 
			#            avec des décomptes :
			#              - assez hauts
			#              - plutôt consécutifs,
			#              - formant une séquence de taille 
			#                de 1 à ~7 fois la longueur de nxbibs
			
			# !! sans se faire piéger par les appels de citation,
			# !! qui provoquent des pics du décompte de matches, mais plus épars 
			
			# Dans l'exemple d'all_occs plus haut, la liste biblio 
			# est sur les lignes [160:170] et commence par [7,3,6,..]
			# Mais le pic à 5 puis 8 est un piège... 
			
			# On peut éviter les pics locaux si on regarde les sommes
			# sur une fenêtre ou chunk de l lignes un peu plus gros
			
			# -----------------------------------------------------
			# large sliding lookahead window over sums in all_occs
			desired_chunk_span = ceil(3.2 * len(xmlbibnodes))
			# param 3.2 fixé après quelques essais 
			# dans doc/tables/test_pdf_bib_zone-pour_ragreage.ods
			
			if debug >= 2:
				print("looking for debut_zone in Σ(occs_i...occs_i+k) over all i, with large window span k", desired_chunk_span, file=sys.stderr)
			
			# score le + haut ==> sera celui de la zone dont les contenus  
			#                     correspondent le plus à ceux des xbibs
			max_chunk = -1
			
			# i correspondant au (dernier) score le plus haut
			i_last_max_chunk = -1
			
			# sums by chunk starting at a given i
			summs_by_chunk_from = []
			
			for i,ici in enumerate(all_occs):
				
				# init sum
				summs_by_chunk_from.append(0)
				
				for k in range(desired_chunk_span):
					# stop count at array end
					if (i + k) >= n_lines:
						break
					# normal case : add freq count
					else:
						summs_by_chunk_from[i] += all_occs[i+k] 
				
				# TODO £ : max normal = last max => simplifier 15 lignes:
				
				# judge last max 
				# (if window span is a little over the real 
				#  length of the bib zone in the pdf
				#  then *last* max should be right answer)
				if summs_by_chunk_from[i] == max_chunk:
					i_last_max_chunk = i
				if summs_by_chunk_from[i] > max_chunk:
					max_chunk = summs_by_chunk_from[i]
					i_last_max_chunk = i
				
				if debug >= 4:
					# affiche chaque step
					print("line", i,
					  "this sum", summs_by_chunk_from[i],
					  "last max sum", max_chunk,
					  "idx of last max", i_last_max_chunk, file=sys.stderr)
			
			if debug >= 3:
				print("windowed sums:", summs_by_chunk_from, file=sys.stderr)
			
			# Décision début
			# --------------
			
			# début: je suis sur que c'est lui !
			debut = i_last_max_chunk
		
		if debug >= 2:
			print("max_chunk:", max_chunk, "\nfrom i:", debut, file=sys.stderr)
		
	# LA FIN
	# ======
	
	# Décision avec petit lookahead
	# ------------------------------
	# on a encore besoin d'une fenêtre
	# mais plus courte (~ 10 lignes)
	# pour trouver la descente
	shorter_span = min(int(len(xmlbibnodes)/2), 10)
	
	if debug >= 2:
		print("looking for fin_zone in Σ(occs_i...occs_i+l) over all i > debut, with with small window span l", shorter_span, file=sys.stderr)
	
	summs_shorter_lookahead = []
	for i in range(n_lines):
		summs_shorter_lookahead.append(0)
		# inutile de se retaper tout le début du doc avant début zone
		if i < debut:
			next
		for l in range(shorter_span):
			if (i + l) >= n_lines:
				break
			else:
				summs_shorter_lookahead[i] += all_occs[i+l]
	
	# curseur temporaire à l'endroit le plus court possible (si une ligne par xbib)
	fin = debut + len(xmlbibnodes)
	
	# prolongement portée jq vraie fin : 
	while summs_shorter_lookahead[fin+1] > 0:
		# tant que freq_suivants > 0:
		# on suppose des continuations consécutive de la liste des biblios
		# ==> on décale la fin
		fin += 1
	
	if debug >= 2:
		print("found probable end of zone at %s", fin, file=sys.stderr)
	
	# log résultat
	print ("deb: ligne %s (\"%s\")\nfin: ligne %s (\"%s\")"
		   %(
		     debut, "_NA_" if debut is None else rawtxtlines[debut] ,
		     fin, "_NA_" if fin is None else rawtxtlines[fin]
		     ),
		  file=sys.stderr)
	
	# filtre si début beaucoup trop tot
	# comparaison len(bibs) len(rawlines)
	if (len(xmlbibnodes) * 8 <  (fin - debut)):
		print ("WARN ça fait trop grand, je remets deb <- None", file=sys.stderr)
		debut = None
	
	return (debut, fin)




def is_searchable(a_string):
	"""Filtre des chaînes texte
		------------------------
		Retourne:
		  - False: chaînes de caractères ne pouvant servir 
		           comme requêtes de recherche
		  - True : toute autre chaîne
	""" 
	return ((a_string is not None) 
	       and (len(a_string) > 1)
	       and (not re.match("^\s+$",a_string))
	       and ( # tout sauf les mots très courts sans majuscules (with, even..)
	               len(a_string) > 4 
	            or re.match("^[A-Z0-9]", a_string)
	           )
	       )


# --------------------------------------------------------







