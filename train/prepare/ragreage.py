#! /usr/bin/python3
"""
TODOS préalables : feuille RSC (et Nat à part)


ragreage.py: Reconstruction de refbibs réelles
             (métadonnées + chaîne d'origine)
             pour créer un corpus d'entraînement
             du modèle CRF "citations" dans Grobid
             
             Si on imagine 2 pôles :
               A- XML data-driven (arbre de structuration de données)
               B- XML text-driven (markup ou annotations d'un texte)
             Alors cet utilitaire cherche à passer de A à B,
             car B est essentiel pour du corpus qui doit servir 
             d'entraînement
             
Principe:
---------
           ARTICLE
           /      \\
      -p PDF     -x XML
      (avec     (biblStruct)
      ponct.)       |
    <pdftotext>     |
        \\         /
         comparaisons
         ------------
      (1) find_bibzone()                => sortie segmentation 
      (2) link_txt_bibs_with_xml()    ===> sortie reference-segmenter
      (3) align xml fields on pdftxt
             ||
           report struct sur non-struct
             ||
            <bibl>
   annotation xml simplifiées* bibl =====> TODO 
    préservant toute l'info markup
     sur chaîne réelle -txtin ou


Entrée:
PDF + <biblStruct>

Sortie:
<bibl> <author>Milgrom, P., &amp; Roberts, J.</author>   (<date>1991</date>).   <title level="a">Adaptive and sophisticated learning in normal form games</title>.   <title level="j">Games and Economic Behavior</title>,  <biblScope type="vol">3</biblScope>,   <biblScope type="pp">82-100</biblScope>. </bibl>

NB: les fonctions et toute la séquence main sauf la fin peuvent convenir
    pour tout travail de type reporter balises dans/sur du non-structuré
"""
__copyright__   = "(c) 2014-15 - INIST-CNRS (projet ISTEX)"
__author__      = "R. Loth"
__status__      = "Development"
__version__     = "1.0"

# TODO strip_tags pour tags trop fins groupés (authors et pp)

# IMPORTS
# =======
# I/O
import sys
import argparse
from lxml import etree

# fonctions
import re
from itertools import permutations
from random import randint

# mes méthodes XML
import rag_xtools # str_escape, strip_inner_tags, glance_xbib, 
                  # simple_path, localname_of_tag

# mes procédures
import rag_procedures  # find_bib_zone, link_txt_bibs_with_xml



# --------------------------------------------------------
# --------------------------------------------------------
# my global vars

NSMAP = {'tei': "http://www.tei-c.org/ns/1.0"}


# pour la tokenisation des lignes via re.findall
re_TOUS = re.compile(r'\w+|[^\w\s]')
re_CONTENUS = re.compile(r'\w+')
re_PONCT = re.compile(r'[^\w\s]')


# each diagnostic whether the xml:ids end with 1,2,3... 
# (TODO: autres diagnostics :
#     -> absents, non numériques, consécutifs avec début != 1 etc)
FLAG_STD_MAP = False

# said endings 1,2,3 (if present) for label retrieval
# utilise l'attribut "n" quand il est présent
# (dans la feuille elsevier il reprenait value-of sb:label)
LABELS = None

# --------------------------------------------------------
# --------------------------------------------------------
# subroutines

def prepare_arg_parser():
	"""Preparation argument parser de l'input pour main"""
	parser = argparse.ArgumentParser(
		description="""Ajout des ponctuations réelles dans un xml de 
		               refbibs (NB lent: ~ 2 doc/s sur 1 thread)""",
		usage="""ragreage.py 
		          -x ech/tei.xml/oup_Human_Molecular_Genetics_ddp278.xml
		          -p ech/pdf/oup_Human_Molecular_Genetics_ddp278.pdf""",
		epilog="- © 2014-15 Inist-CNRS (ISTEX) romain.loth at inist.fr -"
		)
	
	
	parser.add_argument('-x','--xmlin',
		metavar='path/to/xmlfile',
		help="""
		path to a TEI.xml with citations in <biblStruct> xml format 
		(perhaps to be created from native XML by a call like 
		`saxonb-xslt -xsl:tools/Pub2TEI/Stylesheets/Publishers.xsl
		-s:exemples_RONI_1513/rsc_1992_C3_C39920001646.xml`)'""",
		type=str,
		required=True,
		action='store')
		
	
	
	parser.add_argument('-p','--pdfin',
		metavar='path/to/pdffile',
		help="""path to a pdf file of the same text, for attempted
		        pdftottext and citation regexp match""",
		type=str,
		default=None ,  # cf juste en dessous
		action='store')
	
	parser.add_argument('-t','--txtin',
		metavar='path/to/txtfile',
		help="""pdfin can be replaced by a path to a txt flow.
		This input text must be very close to the xml content
		(or segment thereof, in accordance with a chosen -m type)""",
		type=str,
		default=None ,  # cf juste en dessous
		action='store')
		
	
	
	parser.add_argument('-m','--model-type',
		metavar='name-of-model',
		help="""format output as a valid tei's 'listBibl' (default)
		        or tailored to a Grobid crf model pseudotei input among:
		        {'segmentation', 'reference-segmenter', 'citations'}""",
		type=str,
		default='listBibl' ,
		action='store')
	
	
	parser.add_argument('-d','--debug',
		metavar=1,
		type=int,
		help='logging level for debug info in [0-3]',
		default=0,
		action='store')
	
		
	parser.add_argument('-r', '--remainder',
		dest='mask',
		help='show mask after matches instead of normal output',
		action='store_true')
	
	return parser





def check_align_seq_and_correct(array_of_xidx):
	"""
	Diagnostics sur les champions par ligne issus des scores_pl_xb ?
	(signale les séquences en désordre pour diagnostics)
	
	/!\\ fait *une* correction si voisins avant/après sont univoques
	
	Exemple en entrée:
	
	[0, 0, 1, 1, 1, 2, 2, 2, 2, 17, 17, 33, 3, 4, None, None, None, None, None, 4, 4, 4, None, None, None, None, 4, None, None, None, None, 4, None, None, 4, 4, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6, 9, None, None, 7, 7, None, 7, 8, 8, 9, 9, 9, 10, 10, 10, 11, 11, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, None, None, 15, 15, 16, 16, 17, 17, 17, 17, 17, 17, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 4, None, None, None, None, None, 21, 21, 21, 22, 22, 22, 22, 23, 23, 23, 24, 24, 24, 24, 25, 25, 25, 25, 25, 26, 26, 26, 27, 27, None, None, None, 27, 27, 28, 28, 28, 28, 28, 28, 29, 29, 29, 29, 30, 30, 30, 30, 31, 31, 31, 32, 32, 33, 33, 33, None, None, None, None, None, 34, 34, 35, 35, 35, 36, 36, 36, 36, 36, 37, 37, 37, 38, 38, None, None, None, None]
	
	Retour:
	return (is_consec, corrected_array_of_xidx)
	
	(on conserve le None pour toute sortie à caler sur un flux extr)
	"""
	# résultat à valider: "la liste est consécutive"
	is_consec = True
	
	# on ne peut pas faire plus qu'une correction
	did_correc = False
	
	# et on s'arrête après 3 intrus
	is_decale = 0

	# seq <- liste sans duplicat devrait être l'identité
	#        si toutes les biblios sont bien dans le XML src
	#        autrement dit normalement seq[counter] = counter
	seq_counter = 0
	
	# pour vérifications locales:  ( -1 = valeur None )
	#
	# pointeur direct sur dernier qui était != None
	previous_except_none = -1
	# pointeur omnibus sur précédent
	any_previous = -1
	# pointeur omnibus sur suivant
	any_next = -1
	
	# freiner avant le virage
	last_k = len(array_of_xidx)-1
	
	# copie et non pas coref, pour renvoi liste corrigée
	corrected_array_of_xidx = list(array_of_xidx)
	
	# boucle sur l'apparillage
	for k, w in enumerate(array_of_xidx):
		if k+1 <= last_k:
			any_next = array_of_xidx[k+1]
		else:
			any_next = -1
		
		# on saute les lignes vides
		if w is None:
			any_previous = w   # MàJ
			continue
		# et les doublons
		elif w == previous_except_none:
			# là les previous seront à jour
			continue
		else:
			# nouvel élément:
			# ---------------
			seq_counter += 1
			
			# vérif: si nouvel élément normal
			if w == previous_except_none + 1:
				previous_except_none = w    # MàJ
				any_previous = w            # MàJ
				continue
			
			# vérif: si nouvel élément non-consecutif
			else:
				print("SEQ:intrus seq[%i]='%i'" % (seq_counter,w), file=sys.stderr)
				is_decale +=1
				
				if is_decale >= 3:
					print("SEQ: décalage!", file=sys.stderr)
					break
				
				else:
					# -1- tentative de correction
					if not(did_correc) and (any_previous == any_next):
						# on recale l'intrus sur ses voisins
						# NB: eux peuvent encore être None et None
						w = any_previous
						# on reporte
						corrected_array_of_xidx[k] = w
						did_correc = True
						print("SEQ:***corrigé*** sur voisins en '%s'" % w, file=sys.stderr)
						if w is None:
							seq_counter -= 1
						else:
							previous_except_none = w
					# -2- pas d'idée pour corriger
					else:
						is_consec = False
				
				# MAJ pointeur omnibus dans tous les 3 cas
				any_previous = w
				
	
	# bool + array
	return (is_consec, corrected_array_of_xidx)


# --------------------------------------------------------
# fonctions procédures citations (prepare field tokens => match in txt)

def biblStruct_elts_to_match_tokens(xml_elements, debug=0):
	""" Prepares tokens relevant to each field
	
	Convertit une branche XML sous la forme de tous ses sous-éléments
	   en une liste de tokens matchables (instances de XTokinfo)
	   (avec 2 tags src=xip,tgt=xop + 1 ou psieurs contenus=str + 1 re)
	   dont certains spécifiquement groupés pour le modèle crf citations
	
	Difficulté à voir: il peut y avoir plus de tokens que d'éléments
	   par ex: <biblScope unit="page" from="20" to="31" />
	   => donne 2 tokens "20" et "31"
	
	Les tags et la regexp du token sont stockés dans son instance 
	   tag src => xpath simple en y ajoutant les attributs clé
	   tag tgt => tag src traduit via table tei:biblStruct => tei:bibl
	   regexp => match défini dans classe XToken
	"""
	
	toklist = []
	for xelt in xml_elements:
		base_path = rag_xtools.simple_path(xelt, relative_to = "biblStruct")
		
		loc_name = rag_xtools.localname_of_tag(xelt.tag)
		
		if debug >= 2:
			print("***", file=sys.stderr)
			print("base_path   :", base_path, file=sys.stderr)
			print("text content:", xelt.text, file=sys.stderr)
		
		
		# PLUSIEURS CAS PARTICULIERS spécifiques aux biblios
		# -------------------------------------------------------
		# (autrement simplement :  tok.xtexts      = xelt.text 
		#                       et tok.xml_in_path = base_path)
		# -------------------------------------------------------
		
		# cas particulier *date*
		if loc_name == 'date':
			# soit 1 token normal
			if xelt.text:
				tok = XTokinfo(s=xelt.text, xip=base_path)
				toklist.append(tok)
			# soit token dans la valeur d'attribut
			else:
				tok = XTokinfo( s=xelt.get('when'),
				              xip="%s/@%s" % (base_path, 'when') )
				toklist.append(tok)

		# cas particuliers *pagination*: 
		elif loc_name == 'biblScope' and xelt.get('unit') in ['page','pp']:
			# soit un biblScope normal
			if xelt.text:
				tok = XTokinfo( s=xelt.text,
				              xip='%s[@unit="pp"]' % base_path )
				toklist.append(tok)
			# soit 2 tokens dans les attributs
			else:
				tok1 = XTokinfo( s=xelt.get('from'),
				               xip='%s[@unit="pp"]/@from' % base_path)
				tok2 = XTokinfo( s=xelt.get('to'),
				               xip='%s[@unit="pp"]/@to' % base_path )
				toklist.append(tok1, tok2)

		# tous les autres biblScope (vol, iss...) pour préserver leur @unit
		elif loc_name == 'biblScope':
			my_unit = xelt.get('unit')
			tok = XTokinfo( s=xelt.text,
			              xip='%s[@unit="%s"]' % (base_path, my_unit) )
			toklist.append(tok)

		# les title avec leur @level
		# NB : xelt.text is not None devrait aller de soi et pourtant... pub2tei
		elif loc_name == 'title' and xelt.text is not None:
			this_level = xelt.get('level')
			if this_level == None:
				this_level="___"
			tok = XTokinfo( s=xelt.text,
			              xip='%s[@level="%s"]' % (base_path, this_level))
			toklist.append(tok)

		# les noms/prénoms à prendre ensemble quand c'est possible...
		#    pour cela on les traite non pas dans les enfants feuilles
		#    mais le + haut possible ici à (analytic|monogr)/(author|editor)   
		elif loc_name in ['author','editor']:
			# du coup l'arg s du token est différent: str[] et pas str
			str_list = [s for s in xelt.itertext()]
			nametok = XTokinfo( s=str_list,   # <----- ici liste
			                  xip=base_path)
			toklist.append(nametok)
		
		# et du coup on ne re-traite pas tous les enfants du précédent
		elif re.search(r'(?:author|editor)/.', base_path):
			#~ print ("!!!skipping", base_path, xelt.text)
			continue

		# normalement on a déjà traité tous les cas 
		# avec texte vide, attribut intéressant
		# => ne reste que des texte vide inintéressants
		elif xelt.text is None:
			continue

		# === cas normal ===
		else:
			tok = XTokinfo(s=xelt.text, xip=base_path)
			toklist.append(tok)
	
	
	# XTokinfo array
	return toklist


def tok_match_record(matchlist, remainder_str, xtoken, matched_substr):
	"""When an xml token matched a pdf substr, it
	   is recorded by this function in the array
	   'mtched' aka 'matchlist'... It is also removed
	   from the original pdf string (and replaced by 
	   a ref therein) for further tok <=> substr matches.
	   
	   Returns the updated list of substrings + the remainder
	"""
	pstr_infostr = matched_substr
	xtok_infostr = re.sub(r'<([^<>"]{1,3})\w*(?: \w+="([^<>"]{1,3})\w*")?>',
	                     r'\1',
	                    xtoken.tagout)
	# print("SAVE p-substr:'%s' =~ m/%s/ix" % (pstr_infostr,xtok_infostr),file=sys.stderr)
	
	# -a- préparation du substitut balisé en xml
	#      £ pseudo_out == 'rendu'
	pseudo_out = xtoken.tagout+rag_xtools.str_escape(matched_substr)+xtoken.endout
	
	# -b- enregistrement
	matchlist.append(pseudo_out)
	i = len(matchlist)
	
	# -c- effacement dans le remainder
	# (substitution par un renvoi à la \4 ex: ###4###)
	remainder_str = re.sub(xtoken.re, "###%i-%s###" % (i, xtok_infostr), remainder_str)
	
	return(matchlist, remainder_str)


def match_citation_fields(grouped_raw_lines, subtree=None, label="", debug=0):
	"""Matches field info in raw txt string
	   returns(output_xml_string, success_bool)
	   
	   Re-annotate all subelements in subtree this_xbib on
	   a slightly different textstream than the original xml
	   
	   (Minimal: re-annotate only label)
	   
	   (Use case: report des tags <bibl> sur une refbib training)
	
	   TODO cohérence arguments -m "citations" et -r
	
	Séquence :      FLUXTEXTE         XMLNODES
	               grouped_raw         subtree (ou xlabel seul)
	                    |                 |
	                    |               (iter)
	                    |                 |
	                    |             @subelts {xip, xtxt}+
	                    |                 |
	                    |                 |-> biblStruct_elts_to_match_tokens
	                    |                        -> prepare /xregex/
	                    |                        -> prepare <xop> (output tag)
	                    |                                  |
	                    |                  ============== /
	                    |             (XTok.init)
	                    |                 |
	                    |                 |
	                    |              @xtoklist {xip, xtxt, /xre/, <xop>}+
	                    |                 |
	        [état 0]  $remainder          |
	                  @mtched = [] ==>   for xtok in @xtoklist:
	                                      re.findall(/xre/, $remainder)
	                          =======>         |
	                        /                  |
	                       /                  si 1 match  ---- sinon warns++
	                      /                        |
	                    next l                     |
	                     |            tok_match_record()
	   [itération l] ----------------------------------------------
	        où           $remainder.sub(--)
	    l = k+warns      mtched_k ++
	                     @mtched = [ <xop_1>pdfsubtxt_1</xop_1>,
	                                 <xop_2>pdfsubtxt_2</xop_2>,
	                                          (...)
	                                 <xop_k>pdfsubtxt_k</xop_k> ]
	     ---------------------------------------------------------
	                              /
	                             |
	                     reinsertion @mtched dans $remainder
	                                          |
	                                        newxml
	                                          |
	                                    post-traitements (group authors, pp)
	                                          |
	                                 return(newxml, warnings)
	"""
	# vérification des arguments
	if subtree is None and label == "":
		raise ValueError("match_citation_fields()"
		 +" il faut au moins un label ou une branche XML à reporter")
	elif subtree is None:
		just_label = True
	else:
		just_label = False
	
	
	# - log -
	if debug > 0:
		print("\n"+"="*50, file=sys.stderr)
		
		# rappel input XML
		if subtree is not None:
			xmlentry = rag_xtools.glance_xbib(subtree)
			print("XML entry:", xmlentry
		        + "\ncontenus texte xmlbib %i" % j, file=sys.stderr)
			print(etree.tostring(subtree, pretty_print=True).decode("ascii")
		        + ("-"*50), file=sys.stderr)
		else:
			xmlentry = "__no_xbib__"
			print("XML entry:", xmlentry, file=sys.stderr)
		    
		
		# rappel input raw (pdfin ou txtin)
		print("PDF lines: \"%s\"" % grouped_raw_lines, file=sys.stderr)
		print(re_TOUS.findall(grouped_raw_lines), file=sys.stderr)
		print("\n"+"-"*50, file=sys.stderr)
	
	
	# on prépare les infos XML qu'on s'attend à trouver
	# ------------------------
	
	# tokenisation
	#  - - - - - - 
	
	toklist = []
	
	if just_label:
		# ajout du label en 1er token
		toklist = [XTokinfo(s=str(label),xip="label", req=False)]
		#~ print ("je cherche %s" % label)
	
	# sinon tous les autres tokens:
	else:
		
		# NB on ne prend pas le label qui n'est pas concerné par citations
		# mais on pourrait (en reprenant le début de liste du cas préc.) 
		# si on voulait faire un mode 'match intégral'
		
		# parcours de l'arbre
		# -------------------
		# on utilise iter() et pas itertext() qui ne donne pas les chemins
		# + on le fait sous la forme iter(tag=elt) pour avoir les éléments
		#   et pas les commentaires
		subelts = [xelt_s for xelt_s in subtree.iter(tag=etree.Element)]
		
		# la boucle part des éléments xml (contenus attendus) pour
		# créer une liste de tokens avec à réintégrer à l'autre flux:
		#   - les contenus => point d'ancrage qui dira *où* réintégrer
		#                  => génère une expression régulière à trouver
		#   - leur balise  => décrit *ce que* l'on va réintégrer comme infos
		#                  => obtenue par table corresp selon relpath actuel
		# - - - - - - -
		# methode 1 : appel fonction de correspondance cas par cas
		#                    (elle crée les objets "token")
		# TODO liaison (pp debut) (pp last) pour anticiper aphérèse des secondes
		#      ex: 00992399_v16i9_S0099239906818911
		toklist += biblStruct_elts_to_match_tokens(subelts, debug=debug)
		
		# - - - - - - -
		# méthode 2 générique (remettra le même tag qu'en entrée)
		#~ toklist = [XTokinfo(
					  #~ s=xelt.text,
					  #~ xip=rag_xtools.simple_path(
					  #~    xelt, 
					  #~    relative_to = rag_xtools.localname_of_tag(subtree.tag)
					  #~    )
					  #~ ) for xelt in subelts if xelt.text not in [None, ""]]
		
		# print("TOKLIST", toklist)
	
	
	# le flux PDFTXT non encore matché
	# ----------------------------------
	remainder = grouped_raw_lines
	
	
	# on matche les infos XML sur le flux PDFTXT
	# ------------------------------------------
	
	# report des matchs au fur et à mesure
	mtched = []
	mtched_k = -1
	
	# pour vérifs : passé en sortie (TODO plus stat ?)
	unrecognized = False
	
	# correspondances tag d'entrée => le tag de sortie
	for l, tok in enumerate(toklist):
		
		# debg
		my_path = None

		# debug
		if debug >= 2:
			print("XTOK",l,tok, file=sys.stderr)
		
		# sanity check A : the xmlstr we just found
		if tok.xtexts is None:
			print("ERR: no xmlstr for %s" % tok.relpath, file=sys.stderr)
			unrecognized = True
			continue
		
		# 3) on matche -------------------------------------------
		#  £TODO procéder par ordre inverse de longueur (mais \b)|
		#  £TODO faire les tok.req=False en dernier              |
		# print("RAW: {'%s'}" % remainder)                       |
		mgroups = re.findall( tok.re,  remainder )    #          | <<== MATCH
		n_matchs = len(mgroups)                          #       |
		# print("===mgroups==>", mgroups, file=sys.stderr)  #    |
		
		#debg
		if debug >= 2:
			print ("n_matchs:", n_matchs, "(tok.req=", tok.req, ")", file=sys.stderr)
		
		
		# 4) on traite le succès ou non du match -----------------  
		
		# si pas de match => :(
		if n_matchs < 1:
			if tok.req:
				# problème
				unrecognized = True
				if debug >= 2:
					print("WARN: no raw match for XToken '%s' (%s) aka re /%s/" %
							 (tok.xtexts, tok.relpath, tok.re.pattern),
							 file=sys.stderr)
			continue
		
		# si "beaucoup trop" de matchs => :(
		elif n_matchs > 2:
			if tok.req:
				unrecognized = True
				if debug >= 2:
					print("WARN: '%s' (%s) matches too many times (%i)" %
							 (tok.xtexts, tok.relpath, n_matchs),
							 file=sys.stderr)
			
			continue
			
		
		# si deux matchs => :/       (ex: date or city?)
		# we choose arbitrarily one of the 2 matches TODO better
		elif n_matchs == 2:
			if debug >= 2:
				print("WARN: '%s' (%s) matched twice" %
						 (tok.xtexts, tok.relpath),
						 file=sys.stderr)
			
			le_match = mgroups[randint(0, 1)]

			# => it is recorded in the mtched array
			(mtched, remainder) = tok_match_record(mtched, 
			                                        remainder,
			                                         tok,
			                                          le_match)
			mtched_k += 1
			
			continue
		
		# et si on a un unique match => :D
		# n_matchs == 1 ----- on le traite :)
		else:
			# le match est substitué par un renvoi et stocké dans mtched
			# (pour traitement du remainder et ré-insertion ultérieure)
			le_match = mgroups[0]
			
			# xml token matched le_match pdf str
			# => recorded in mtched array
			(mtched, remainder) = tok_match_record(mtched, 
			                                        remainder,
			                                         tok,
			                                          le_match)
			mtched_k += 1
			
			# £TODO utiliser les possibilités du remainder (ou masque des infos):
			#  - diagnostic qualité sortie (moins bonne si remainder grand)
			
			# ----------------------------------8<----------------------
			# au passage stat comparaison facultative:
			# chaines à erreurs OCR <=> chaines corrigées
			if tok.combimode == False and le_match != tok.xtexts:
				if re.sub('-','',le_match) == re.sub('-','',tok.xtexts):
					print("MATCH interpolé tiret:\n\tPDF:'%s'\n\tXML:'%s'" 
					         % (le_match, tok.xtexts),
					      file=sys.stderr)
				elif re.sub('[- ]','',le_match) == re.sub('[- ]','',tok.xtexts):
					print("MATCH interpolé espaces:\n\tPDF:'%s'\n\tXML:'%s'" 
					         % (le_match, tok.xtexts),
					      file=sys.stderr)
				else:
					print("MATCH interpolé OCR:\n\tPDF:'%s'\n\tXML:'%s'" 
					         % (le_match, tok.xtexts),
					      file=sys.stderr)
			# ----------------------------------8<----------------------
		
		# fins cas de figures match
	# fin boucle sur tokens
	
	# print("$remainder:", remainder, file=sys.stderr)
	# print("@mtched   :", mtched, file=sys.stderr)
	
	# traitement du remainder => résultat visible avec option -r (mask)
	remainder = rag_xtools.str_escape(remainder)
	
	# affiche la pile récupérée
	#~ print("====MATCHED====", mtched, file=sys.stderr)
	
	
	# SORTIE 
	
	# c'est ce "remainder" qu'on affichera si args.mask
	new_xml = remainder

	# sinon ré-insertion des matchs échappés eux aussi ET balisés
	if not args.mask:
		for (k, rendu) in enumerate(mtched):
			renvoi = "###%i###" % (k + 1)
			# ==================================
			new_xml = re.sub(renvoi, rendu,
									 new_xml)
			
		# correctif label  => TODO à part dans une matcheuse que pour label?
		# ---------------
		#   Les labels sont souvents des attributs n=int mais
		#   dans le corpus d'entraînement on les balise avec leur ponct
		#   ex: [<label>1</label>]  ==> <label>[1]</label>
		new_xml = re.sub("\[<label>(.*?)</label>\]",
							 "<label>[\g<1>]</label>",
							   new_xml)
		
		# dernier correctif: groupements de tags
		# ------------------
		
		# -a- pages collées pour le modèle citation
		new_xml = re.sub(r'<pp>', r'<biblScope type="pp">',
				  re.sub(r'</pp>', r'</biblScope>',
				 re.sub(r'(<pp>.*</pp>)',rag_xtools.strip_inner_tags,
				new_xml)))
		
		# -b- auteurs groupés
		# ex <author>Ageta, H.</author>, <author>Arai, Y.</author> 
		#        => <author>Ageta, H., Arai, Y.</author>
		new_xml = re.sub(r'(<author>.*</author>)',
							  rag_xtools.strip_inner_tags, 
							new_xml)
		new_xml = re.sub(r'(<editor>.*</editor>)',
							  rag_xtools.strip_inner_tags,
							new_xml)
	
	
	# ajout d'un éventuel tag extérieur
	# ----------------------------------
	new_xml = "<bibl>"+new_xml+"</bibl>"
	
	# ==> (new_xml, success_bool)
	return(new_xml, not(unrecognized))


# --------------------------------------------------------

# --------------------------------------------------------


class XTokinfo:
	"""Groups infos about a str token found in the source XML"""
	
	# sert pour recombiner des tokens séparés: par ex " " ou ""
	BLANK = " "
	
	# pour matcher malgré des erreurs OCR
	OCR_SIMILAR_CHARACTER = {
	  '0' : ['0', 'O'],
	  '1' : ['1','l'],
	  '5' : ['S', '5'],
	  'a' : ['a', 'u', 'n'],
	  'ä' : ['ä', 'a', 'g', 'L'],
	  'c' : ['c', 'e', 't'],
	  'ç' : ['ç', 'q'],
	  'd' : ['d', 'cl'],
	  'e' : ['e', 'c', '¢'],
	  'é' : ['é', '6', 'e', 'd', '~'],
	  'è' : ['è', 'e', 'Q'],
	  'f' : ['f', 't'],
	  'i' : ['i', ';'],
	  'l' : ['1', 'l', 'i','I', ']', '/', 'Z'],
	  'm' : ['m', 'rn', 'nn'],   # comment faire les règles inverses 2->1 :/ ?
	  'n' : ['n', 'rt', 'll'],
	  'o' : ['o', 'c'],
	  'ø' : ['ø', 'o'],
	  'ö' : ['ö', 'o', '6', 'b', '~'],
	  't' : ['t', 'f', '¹', 'r'],
	  'ü' : ['ü', 'u', 'ii', 'ti', 'fi'],
	  'v' : ['v', 'y'],
	  'y' : ['y', 'v'],
	  'D' : ['D', 'I)'],
	  'E' : ['E', 'B'],
	  'F' : ['F', 'E'],
	  'J' : ['J', '.I'],
	  'O' : ['O', '0', 'C)'],
	  'P' : ['P', "I'"],
	  'R' : ['R', 'K'],
	  'S' : ['S', '5'],
	  'V' : ['V', 'Y'],
	  'Y' : ['Y', 'V'],
	  'β' : ['β', '[3', 'b', 'fl'],
	
	  #~ '.' : ['.', ','],       # risque de choper un séparateur en trop
	  '—' : ['—', '--', '-'],
	  '"' : ['"','“','”','‟'],
	  '“' : ['"','“','”','‟'],
	  '”' : ['"','“','”','‟'],
	  '‟' : ['"','“','”','‟'],
	  "'" : ["'","‘","’","‛"],
	  "‘" : ["'","‘","’","‛"],
	  "’" : ["'","‘","’","‛"],
	  "‛" : ["'","‘","’","‛"]
	}
	
	OCR_CLASSES = OCR_SIMILAR_CHARACTER.keys()
	
	# £ TODO define ~ config.IN_TO_OUT with param table
	# MAP (biblStruct => bibl) to choose the final citation's 'out tag'
	STRUCT_TO_BIBL = {
	  # --- label inséré à part ---
	  'label': '<label>',
	  
	  # --- équivalences standard ---
	  'analytic/title[@level="a"]' :            '<title level="a">',
	  'analytic/title/hi' :                 '__rmtag__',  # todo effacer le tag
	  'analytic/title/title/hi' :           '__rmtag__',
	  'analytic/translated-title/maintitle':'<note>',     # pour CRF
	  'analytic/author/persName/surname' :  '<author>',
	  'analytic/author/persName/forename': '<author>',
	  'analytic/author/forename' :          '<author>',
	  'analytic/author/surname' :           '<author>',
	  'analytic/author/orgName' :           '<author>',  # ? orgName en <bibl> ?
	  'analytic/author' :                   '<author>',
	  'analytic/name' :                     '<author>',  # wtf?
	  'analytic/respStmt/name' :            '<author>',
	  'monogr/author/persName/surname' :       '<author>',  # <!-- monogr -->
	  'monogr/author/persName/forename' :        '<author>',
	  'monogr/author/orgName' :                   '<author>',  # ? orgName en <bibl> ?
	  'monogr/author' :                           '<author>',
	  'monogr/respStmt/name' :                    '<author>',
	  'monogr/imprint/meeting' :                  '<title level="m">',
	  'monogr/meeting' :                          '<title level="m">',
	  'monogr/imprint/date' :                     '<date>',
	  'monogr/imprint/date/@when' :               '<date>',
	  'monogr/title[@level="j"]' :                '<title level="j">',
	  'monogr/title[@level="m"]' :                '<title level="m">',
	  
	  'monogr/imprint/biblScope[@unit="vol"]' :   '<biblScope type="vol">',
	  'monogr/imprint/biblScope[@unit="issue"]': '<biblScope type="issue">',
	  'monogr/imprint/biblScope[@unit="part"]' :  '<biblScope type="chapter">',
	  'monogr/imprint/biblScope[@unit="chap"]' :  '<biblScope type="chapter">',
	  'monogr/imprint/publisher' :                '<publisher>',
	  'monogr/imprint/pubPlace' :                 '<pubPlace>',
	  'monogr/meeting/placeName' :                '<pubPlace>',
	  'monogr/editor/persName/surname' :       '<editor>',
	  'monogr/editor/persName/forename' :      '<editor>',
	  'monogr/editor' :                        '<editor>',
	  'series/title[@level="s"]' :          '<title level="s">',
	  'series/biblScope[@unit="vol"]' :     '<biblScope type="vol">',
	  'note' :                              '<note>',
	   #£ TODO cas particulier thèse ou rapport => <note type="report">
	  'note/p' :                            '<note>',
	  'monogr/idno' :                       '<idno>',
	  'analytic/idno' :                     '<editor>',
	  'note/ref' :                          '<ptr type="web">',
	  'ref' :                               '<ptr type="web">',
	  
	  # --- pages ---
	  # pour fusion ulterieure de 2 tags <pp> ensemble
	  'monogr/imprint/biblScope[@unit="pp"]': '<pp>',
	  # sinon normal:
	  # 'monogr/imprint/biblScope[@unit="pp"]': '<biblScope type="pp">',
	  
	  # --- cas particuliers ---
	  # if bS has note which contains « thesis », publisher is a university
	  # 'monogr/imprint/publisher': 'orgName',
	  
	  # -- à vérifier --
	  'monogr/imprint/edition' :                  '<note type="edition">',  
	  }
	
	
	
	# =================================================
	# initialisation
	def __init__(self, s="", xip="", req=True):
		# 1) Initialisation str <= contenu(s) et xip <= src_path
		# -------------------------------------------------------
		
		# << XIP
		self.relpath = xip   # xpath of src element
		
		# << contents: SELF.XTEXTS
		
		# -a- 
		# 1 token = 1 str (<= usually text content of the xml elt)
		if type(s) == str:
			self.xtexts = s
			self.combimode = False
		
		# -b- 
		# 1 token = k strings together in any order
		# initialisation combinée avec une liste str (ex: nom + prénom)
		elif type(s) == list:
			self.xtexts = s
			self.combimode = True
		
		else:
			raise TypeError(type(s))
		
		# <<  "isRequired" BOOL
		#    (ex: label not required)
		# /!\ most tokens are required for successful align
		self.req = req
		
		# 2) on prépare des expressions régulières pour le contenu
		# ---------------------------------------------------------
		# <> SELF.RE
		# "J Appl Phys" ==> r'J(\W+)Appl(\W+)Phys'
		#  si tiret autorisé encore + complexe:
		#               ==> r'(?=^.{11,15}$)J(\W+)A[-¤]{0,2}p[-¤]{0,2}p[-¤]\ #
		#                     {0,2}l(\W+)P[-¤]{0,2}h[-¤]{0,2}y[-¤]{0,2}s'
		# => les chaînes "combimode" seront matchables dans les 2 ordres possibles
		# ex: /nom\W*prénom/ et /prénom\W*nom/
		self.re = self.tok_full_regexp()
		
		# 3) on prépare ce qui deviendra le tag de sortie
		# ------------------------------------------------
		# <> SELF.TAGOUT
		# opening tag
		self.tagout = XTokinfo.xmlin_path_to_xmlout(self.relpath)
		# closing tag
		self.endout = re.sub(r'^<','</', re.sub(r' .*$','>', self.tagout))
		
	
	# =================================================
	# correspondance des annotations I/O
	def xmlin_path_to_xmlout(relpath, context=None):
		"""
		Translate an input structrured path into desired output markup
		"""
		
		markup_xpath = '__inconnu__'
		try:
			# for this we use the global var : STRUCT_TO_BIBL
			markup_xpath=XTokinfo.STRUCT_TO_BIBL[relpath]
		except KeyError as ke:
			print("KeyError: '%s' n'est pas dans ma liste..." % relpath)
		
		return markup_xpath
	
	
	
	# =================================================
	# préparation d'une regexp pour un *string* donné
	#          (ne pas tenir compte du self)
	def str_pre_regexp(self, anystring):
		"""Just the raw regexp string without capture"""
		
		strlen = len(anystring)
		
		# A) préparation du contenu
		# --------------------------
		subtokens = re_TOUS.findall(anystring)
		
		# £TODO params
		do_cesure=True
		do_espace=True
		do_char_classes=True
		
		# on ne fait pas la césure pour les locutions courtes
		if (not do_cesure or strlen < 6):
			# re: chaîne de base 
			# ------------------
			# autorisant un ou des passage-s à la ligne à ch. espace entre ch. mot
			my_re_str = '[\W¤]{0,10}'.join(r"%s" % u for u in subtokens)
		
		# expression plus complexe pour permettre une césure inattendue
		else:
			minlen = strlen
			# on permet 3 caractères en plus tous les 80 caractères
			maxlen = strlen + ((strlen // 80)+1) * 3
			
			# exprime la contrainte de longueur de la regex qui suivra
			re_length_prefix = r"(?=.{%i,%i})" % (minlen, maxlen)
			
			# on va ajouter /-?/ après ch. caractère...
			# version avec sauts de lignes et espaces : on ajouterait /[-¤ ]{0,3}/
			virtually_hyphenated_esctokens = []
			
			# ... de ch token...
			for u in subtokens:
				v_h_word=""
				# ... donc pour ch. caractère !
				for c in u:
					if not do_char_classes or (c not in XTokinfo.OCR_CLASSES):
						v_h_word += re.escape(c) + '[- ]?'
					
					else:
						# todo ici classes de caractères 'semblables'
						c_matchables = XTokinfo.OCR_SIMILAR_CHARACTER[c]
						c_alter = '|'.join(map(re.escape,c_matchables))
						
						# ex : regexp = '(?:i|l)'
						v_h_word += '(?:' + c_alter + ')' + '-?'
				
				virtually_hyphenated_esctokens.append(v_h_word)
				
				my_re_str = re_length_prefix+'[\W¤]*'.join(r"%s" % u 
				                       for u in virtually_hyphenated_esctokens)
			
			# ex: ['M[- ]?o[- ]?l[- ]?e[- ]?c[- ]?u[- ]?l[- ]?a[- ]?r[- ]?',
			#      '\\&', 'C[- ]?e[- ]?l[- ]?l[- ]?u[- ]?l[- ]?a[- ]?r[- ]?',
			#      'E[- ]?n[- ]?d[- ]?o[- ]?c[- ]?r[- ]?i[- ]?
			#      n[- ]?o[- ]?l[- ]?o[- ]?g[- ]?y[- ]?']
			#
			# <title level="j">Molecular &amp; Cellular Endocrinology</title>
			
			#~ print('====V_H_Toks====', virtually_hyphenated_esctokens, file=sys.stderr)
		
		
		#~ print("====x_str====", anystring, file=sys.stderr)
		#~ print("====re_str====", my_re_st file=sys.stderr)
		
		
		# B) Décision du format des limites gauche et droite pour les \b
		# --------------------------------------------------
		# test si commence par une ponctuation
		if re.search(r'^\W', subtokens[0]):
			re_boundary_prefix = ""
		else:
			re_boundary_prefix = "\\b"
		# idem à la fin
		if re.search(r'\W$', subtokens[-1]):
			re_boundary_postfix = ""
		else:
			re_boundary_postfix = "\\b"
		
		# voilà
		return re_boundary_prefix + my_re_str + re_boundary_postfix
	
	
	
	
	# =================================================
	# construction de l'expression régulière à partir
	# de toutes sortes de strings seuls ou couplés
	def tok_full_regexp(self):
		"""The precompiled regexp with alternatives and parentheses around"""
		re_str=""
		
		# => cas normal : une seule chaîne dans self.xtexts
		if not self.combimode:
			# récup d'une seule chaîne échappée
			re_str = self.str_pre_regexp(self.xtexts)
		
		# => plusieurs chaînes matchables dans les 2 ordres possibles
		# (quand les XML n'ont pas préservé l'ordre)
		elif self.combimode:
			alternatives = []
			# ex: ['nom', 'prénom'] => /((?:nom\W*prénom)|(?:prénom\W*nom))/
			for substr_combi in permutations(self.xtexts):
				# jonction par un espace ou toute valeur de XTokinfo.BLANK
				str_combi = XTokinfo.BLANK.join(substr_combi)
				re_combi = self.str_pre_regexp(str_combi)
				
				# non capturing
				alternatives.append("(?:"+re_combi+")")
			
			# -or- using regex pipe
			re_str = "|".join(alternatives)
		
		# enfin ajout de balises de capture extérieures
		# et compilation CASE INSENSITIve !
		my_regexp_object = re.compile("("+re_str+")", re.IGNORECASE)
		return my_regexp_object
	
	
	def __str__(self):
		return "%s : '%s' : %s" % (self.relpath, self.xtexts, self.tagout)
		# return "'%s' : %s" % (self.xtexts, self.tagout)
	
	def __repr__(self):
		return "<%s>" % self.__str__()

# --------------------------------------------------------

# --------------------------------------------------------
















###############################################################
########################### M A I N ###########################
###############################################################

# logstamp
# ========
# represents hope that all 3 steps go well
checklist = [True, True, True]

# options et arguments
# ====================
parser = prepare_arg_parser()
args = parser.parse_args(sys.argv[1:])

# défault pdfin
if args.pdfin == None and args.txtin == None :
	temp = re.sub(r'tei.xml', r'pdf', args.xmlin)
	temp = re.sub(r'teixml', r'pdf', temp)
	temp = re.sub(r'tei', r'pdf', temp)
	args.pdfin = re.sub(r'xml', r'pdf', temp)
	print("PDFIN?: essai de %s" % args.pdfin, file=sys.stderr)

# vérification cohérence
if (args.model_type in ["reference-segmenter", "citations"] 
	and not args.txtin):
	print("""L'arg -m '%s' requiert un -t ad hoc (utiliser les cibles createTraining* de grobid-trainer)"""
		  % args.model_type,
		  file=sys.stderr)
	sys.exit(1)


#    INPUT XML
# ================
print("LECTURE XML", file=sys.stderr)

parser = etree.XMLParser(remove_blank_text=True)

# parse parse
try:
	dom = etree.parse(args.xmlin, parser)

except OSError as e:
	print(e)
	sys.exit(1)

except etree.XMLSyntaxError as e:
	print("lxml.etree:", e)
	sys.exit(1)

# stockage DOCID
DOCID = "RAG-"+re.sub( "\.xml$", # sans suffixe
                "",
                # sans dossiers
                re.sub("^.*/([^/]+)$", r"\1", args.xmlin)
               )

# query query
xbibs = dom.findall(
			"tei:text/tei:back//tei:listBibl/tei:biblStruct",
			namespaces=NSMAP
			)
xbibs_plus = dom.xpath(
			"tei:text/tei:back//tei:listBibl/*[local-name()='bibl' or local-name()='biblStruct']",
			 namespaces=NSMAP
			)

nxb = len(xbibs_plus)
print ("N xbibs: %i" % nxb, file=sys.stderr)

# pour logs
# ---------
nxb_traitables = len(xbibs)
nxbof = nxb - nxb_traitables

# si présence de <bibl>
if (nxbof > 0):
	print("WARN: %i entrées dont  %i <bibl> (non traitées)" %
			 (nxb, nxbof),
			 file=sys.stderr )
	
	# incomplétude du résultat à l'étape 0
	checklist[0] = False
	
	
	# TODO : traiter les <bibl> ssi sortie refseg 
	# + les prendre en compte dans le décompte de enumerate(xbibs)

# exception si aucune <biblStruct>
if (nxb == 0):
	print("ERR: aucune xbib <biblStruct> dans ce xml natif !",
			 file=sys.stderr)
	sys.exit(1)


# préalable: passage en revue des XML ~> diagnostics IDs
# ----------
# initialisation IDs et NOs
xml_ids_map = [None for j in range(nxb)]
xml_no_strs_map = [None for j in range(nxb)]
xml_no_ints_map = [None for j in range(nxb)]

# remplissage selon xpaths @id et @n
for j, xbib in enumerate(xbibs):
	
	# il devrait toujours y avoir un ID, mais en réalité parfois absent
	xbib_id_nodes = xbib.xpath("@xml:id") ;
	
	# si présent, l'attribut "@n" reprend le label (devrait toujours être numérique ?)
	xbib_no_nodes = xbib.xpath("@n") ;
	
	found_id = (len(xbib_id_nodes) == 1)
	found_no = (len(xbib_no_nodes) == 1 
				  and re.match(r'^[\[\]\.0-9 ]+$', str(xbib_no_nodes[0])))
	
	# récup id et numérotation
	if found_id and found_no:
		# lecture attributs XML
		thisbib_id = xbib_id_nodes.pop()
		thisbib_no_str = xbib_no_nodes.pop()
		thisbib_no_int = int(re.sub("[^0-9]+","", thisbib_no_str))
	
	# récup id et astuce numérotation attendue en fin d'ID 
	elif found_id and not found_no:
		thisbib_id = xbib_id_nodes.pop()
		
		# on cherche le dernier nombre pour mettre dans xml_nos_map
		# par ex: 1,2 ou 3 dans DDP278C1 DDP278C2 DDP278C3
		postfix_num_match = re.search(r"[0-9]+$", thisbib_id)
		
		if postfix_num_match:
			thisbib_no_str = postfix_num_match.group(0)
			thisbib_no_int = postfix_num_match.group(0)
		else:
			# rien trouvé pour le no: on mettra None dans xml_nos_map
			thisbib_no_str = None
			thisbib_no_int = None
	
	# les 2 cas restants: trouvé no sans id OU trouvé aucun
	else:
		thisbib_id = None
		thisbib_no_str = None
		thisbib_no_int = None
	
	# stockage des labels/bibids trouvés
	# -----------------------------------
	xml_ids_map[j] = thisbib_id
	xml_no_strs_map[j] = thisbib_no_str
	xml_no_ints_map[j] = thisbib_no_int
	

# verif incrément normal a posteriori 
# (ce diagnostic pourrait aussi être fait dès la boucle) 
FLAG_STD_MAP = True # temporaire
for j, no in enumerate(xml_no_ints_map):
	if (no is None) or (int(no) != j+1):
		FLAG_STD_MAP = False


# écriture dans variable globale pour matcher les labels réels en sortie
LABELS = []
for item in xml_no_strs_map:
	if item is None:
		LABELS.append(None)
	else:
		# remove padding 0s
		no = re.sub("^0+", "", item)
		LABELS.append(no)


if args.debug >= 1:
	print("IDs:", xml_ids_map, file=sys.stderr)
	print("NOs:", xml_no_ints_map, file=sys.stderr)
	print("NO_strs:", xml_no_strs_map, file=sys.stderr)
	if FLAG_STD_MAP:
		print("GOOD: numérotation ID <> LABEL traditionnelle",
				 file=sys.stderr)
	else:
		# todo préciser le type de lacune observée :
		# (pas du tout de labels, ID avec plusieurs ints, ou gap dans la seq)
		print("WARN: la numérotation XML:ID non incrémentale",
				 file=sys.stderr)

# // fin lecture xml bibs


if args.txtin:
	#  INPUT TXT à comparer
	# ======================
	print("---\nLECTURE FLUX TXT ISSU DE PDF", file=sys.stderr)
	
	try:
		rawlines = [line.rstrip('\n') for line in open(args.txtin)]
	except FileNotFoundError as e:
		print("I/O ERR: Echec ouverture du flux textin '%s': %s\n"
				  % (e.filename,e.strerror),
				  file=sys.stderr)
		sys.exit(1)

elif args.pdfin:
	#  INPUT PDF à comparer
	# ======================
	print("---\nLECTURE PDF", file=sys.stderr)

	# appel pdftotext via OS
	try:
		pdftxt = check_output(['pdftotext', args.pdfin, '-']).decode("utf-8")
	
	except CalledProcessError as e:
		print("LIB ERR: Echec pdftotxt: cmdcall: '%s'\n  ==> failed (file not found?)" % e.cmd, file=sys.stderr)
		# print(e.output, file=sys.stderr)
		sys.exit(1)
	# got our pdf text!
	rawlines = [line for line in pdftxt.split("\n")]

else:
	print("""ARG ERR: On attend ici --pdfin foo.pdf
			 (ou alors --txtin bar.txt)""",
			 file=sys.stderr)
	sys.exit(1)


# pour logs
# ---------
npl = len(rawlines)

print ("N lignes: %i" % npl, file=sys.stderr)


# La zone biblio dans le texte  pdf est un segment marqué par 2 bornes
#       (par ex: d=60 et f=61 on aura |2| lignes intéressantes)
# ----------------------------------------------------------------------
debut_zone = None
fin_zone = None


#    ============
# -a- Cas facile
# (si on a un txtin visant 'citations' ou 'reference-segmenter'
#  en entraînement, le flux ne contient déjà *que* la zone des biblios
if (args.model_type in ["reference-segmenter", "citations"]):
	debut_zone = 0
	fin_zone = npl -1 

#            =======================
# -b- sinon : Recherche zone biblio
else:
	print("---\nFIND PDF BIBS", file=sys.stderr)
	
	(debut_zone, fin_zone) = rag_procedures.find_bib_zone(
									 xbibs_plus,
									 rawlines,
									 debug=args.debug
							  )
	
	#  !! debut_zone et fin_zone sont des bornes inclusives !!
	#  !!         donc nos slices utiliseront fin+1         !!
	#                      ------             -----
	
	if ((debut_zone == None) or  (fin_zone == None)):
		print("ERR: trop difficile de trouver la zone biblio dans ce rawtexte '%s'" % args.pdfin, file=sys.stderr)
		sys.exit(1)


# (à présent: match inverse pour aligner)
# =======================================
#  Alignement lignes txt <=> entrées XML
# =======================================
print("---\nLINK PDF BIBS <=> XML BIBS", file=sys.stderr)

# get correspondance array
# (sequence over pdf content lines ids filled with matching xml ids)
winners = rag_procedures.link_txt_bibs_with_xml(
				   rawlines[debut_zone:fin_zone+1], 
				   xbibs, 
				   debug=args.debug
				   )

# affiche résultat
print("Les champions: %s" % winners, file=sys.stderr)
# exemple liste winners
# ----------------------------
# winners =[None, 0 , 0 , 1 , 1 , 2, 2, 2, 3, 3, 3, 4, 4, None, None, None, None, 4, 5, 5, 6, 6, 7,   7                 ]
#      i' =[  0 | 1 | 2 | 3 | 4 | ...     ...     ...     ...     ...     ...     ...     ...     | fin_zone-debut_zone ]

# NB: "None" values are either:
#             - failed matches
#             - or gaps in the list,
#             - or lines before 1st ref
#             - or lines after last ref


# TODO ici utilisation de xml_nos_map pour faire des tokens labels

# vérification si on ne doit garder que les documents qui matchent bien
# (quand on génère un corpus d'entraînement)
# voire correction si évident
(is_consec, new_winners) = check_align_seq_and_correct(winners)

if new_winners != winners:
	print("Ces champions corrigés: %s" % new_winners, file=sys.stderr)
	winners = new_winners

if not is_consec:
	# désordre du résultat à l'étape 1
	checklist[1] = False



print("simple checklist so far:" , checklist[0:2], file=sys.stderr)


# -------=================----------------------------------------
# boucle OUTPUT --mode seg (objectif: repérage macro zone de bibs)
# -------=================----------------------------------------
#
#   Contenus des bibs sont connus (TEI in) mais le flux du texte
#   (PDF in) est légèrement différent
#
#   use case: entraînement seg pour grobid
#
	 # TODO
	


# -------====================---------------------------------
# boucle OUTPUT --mode refseg (objectif: alignements de bibs)
# -------====================---------------------------------
if args.model_type=="reference-segmenter":
	
	# log de la checkliste (évaluation qualité de ce qui sort)
	# non nécessaire pour les citations (mis inline)
	CHECKS = open("checks.refseg.tab", "a")

	# header
	header="""<tei>
<teiHeader>
	<fileDesc xml:id="%s"/>
</teiHeader>
<text xml:lang="en">
	<listBibl>""" % DOCID
	print (header)
	
	# yalla !
	print ("~" * 80, file=sys.stderr)
	
	# buffer for lines of the same xml elt
	local_grouped_lines = []
	
	# txtin donc len(winners) = len(rawlines)
	if len(winners) != len(rawlines):
		raise ValueError("wtf??")
	
	# ne pas oublier de rajouter un marqueur fin de lignes après ch. rawlines
	for i, this_line in enumerate(rawlines):
		
		# récup de l'indice XML correspondant à la ligne
		j_win = winners[i]
		
		# lookahead de l'indice suivant
		if i+1 < npl:
			next_win = winners[i+1]
		else:
			next_win = None
		
		# cas aucune ligne matchée
		if j_win is None:
			# on ne peut rien reporter sur cette ligne
			# mais on la sort quand même (fidélité au flux txtin)
			print(rag_xtools.str_escape(this_line)+"<lb/>")
			#                           -------
			#                           important!
		else:
			# nouveau morceau
			if len(local_grouped_lines) is 0:
				# tentative de report du label
				xlabel = LABELS[j_win]
				if xlabel:
					# TODO faire une fonction à part et reserver match_citation_fields au cas citations ?
					# -------------------8<-------------------------
					# report du label sur chaîne de caractères réelle
					(my_bibl_line, success) = match_citation_fields(
					                            this_line,
					                            label = xlabel,
					                            debug = args.debug,
					                           )
					
					# match_cit_field n'a pas été prévu pour multiligne: TODO à part ?
					my_bibl_line = re.sub("</bibl>$","",my_bibl_line)
					
					# les labels sont souvents des attributs n=int mais
					# dans le corpus d'entraînement on les balise avec leur ponct
					# ex: [<label>1</label>]  ==> <label>[1]</label>
					my_bibl_line = re.sub("\[<label>(.*?)</label>\]",
					                       "<label>\[\1\]</label>",
					                       my_bibl_line)
					# -------------------8<-------------------------
				else:
					my_bibl_line = "<bibl>"+ rag_xtools.str_escape(my_bibl_line)
				
				# >> BUFFER, dans les 2 cas
				local_grouped_lines.append(my_bibl_line)

			# morceaux de suite
			elif next_win == j_win:
				# ligne sans balises
				local_grouped_lines.append(rag_xtools.str_escape(this_line))
			# morceau de fin >> SORTIE
			else:
				local_grouped_lines.append(rag_xtools.str_escape(this_line)+'<lb/></bibl>')
				#                                                ------
				#                                               fin de la
				#                                             dernière ligne
				
				# separateur saut de ligne pour les lignes internes
				#  => sortie finale format ref-seg
				#     -------------
				print("<lb/>".join(local_grouped_lines))
				
				# empty buffer
				local_grouped_lines = []
	
	# diagnostic
	diagno_refseg = args.xmlin+"\t"+str(int(checklist[0]))+"\t"+str(int(checklist[1]))
	print ("DIAGNOSTIC RAPIDE", diagno_refseg, file=sys.stderr)
	
	print ("~" * 80, file=sys.stderr)
	print (diagno_refseg , file=CHECKS)
	
	CHECKS.close()
	
	# tail
	tail="""
	</listBibl>
</text>
</tei>"""
	print (tail)
	
	sys.exit(0)

# -------------------------------------------------------------
#  mode 2: boucle plus simple pour les sorties + "standardes"
# -------------------------------------------------------------
#    in std mode we go further by grouping content from pdf
#     (each raw txtline i') by its associated xml id j_win
#   --------------------------------------------------------
else:
	
	# résultat à remplir
	rawlinegroups_by_xid = [None for j in range(nxb)]
	
	for i_prime, j_win in enumerate(winners):
		if j_win is None:
			# we *ignore* None values 
			# => if we wanted them we need to fix them earlier
			pass
		# === normal case ===
		else:
			# nouveau morceau
			if rawlinegroups_by_xid[j_win] is None:
				rawlinegroups_by_xid[j_win] = rawlines[debut_zone+i_prime]
			# morceaux de suite
			else:
				# on recolle les lignes successives d'une même bib
				# separateur saut de ligne: '¤' ASCII 207
				#  => format sortie citations: neutre dans les reports car matche /\W+/
				rawlinegroups_by_xid[j_win] += "¤"+rawlines[debut_zone+i_prime]
	
	# log détaillé de cette étape
	if args.debug >= 1:
		# linked results
		print("="*70, file=sys.stderr)
		for j in range(nxb):
			xml_info = rag_xtools.glance_xbib(xbibs[j], longer = True)
			if rawlinegroups_by_xid[j] is None:
				print(xml_info + "\n<==> NONE", file=sys.stderr)
			else:
				print(xml_info + "\n<==>\n" + rawlinegroups_by_xid[j], file=sys.stderr)
			print("="*70, file=sys.stderr)
	
	
	#       ------------------------------------          =============
	#  Enfin alignement des champs sur le texte et boucle OUTPUT mode 2
	#       ------------------------------------          =============
	print("---\nLINK PBIB TOKENS <=> XBIB FIELDS\n", file=sys.stderr)
	
	# report de chaque champ
	bibl_found_array = []
	
	max_j = len(rawlinegroups_by_xid) - 1
	
	for j, group_of_real_lines in enumerate(rawlinegroups_by_xid):
			
			# la dernière est parfois vide
			if (group_of_real_lines is None) and (j == max_j):
				continue
			
			try:
				this_xbib = xbibs[j]
			except IndexError as ie:
				print("Bib %i absente dans xbibs pour '%s'" % 
				               ( j, 
				                 group_of_real_lines ),
				file=sys.stderr)
				# on donne un biblStruct vide
				this_xbib = etree.Element('biblStruct', type="__xbib_non_listée__")
			
			xlabel = LABELS[j]
			
			toks = []
			
			if group_of_real_lines is None:
				if args.debug > 1:
					print("===:no lines found for xbib %i (label %s)"
							 % (j,xlabel))
				
				# incomplétude constatée du résultat à l'étape link_lines
				checklist[1] = False
				continue
			
			else:
				# report des balises sur chaîne de caractères réelle
				(my_bibl_str, success) = match_citation_fields(
											group_of_real_lines,
											subtree = this_xbib,
											label   = xlabel,
											debug   = args.debug
										   )
				#~ if not success:
					#~ print("KEIN SUCCESS")
				
				# update 3è slot checklist pour filtrage erreurs
				# (1 info par refbib et non plus sur l'ens.)
				checklist[2] = success
				
				# separateur saut de ligne dans le cas 'citations' 
				# (TODO check si c'est bien " " attendu et pas "" ?)
				my_bibl_str = re.sub("¤"," ",my_bibl_str)
				
				# pour la sortie : filtre ex: 111 => tout bon
				# traduction de la checkliste en "101", "111", etc
				out_check_trigram = "".join([str(int(boul)) 
				                              for boul in checklist])
				
				#  => sortie finale format 'citations'
				#     -------------
				print(out_check_trigram+":"+my_bibl_str)
	
	
	# EXEMPLES DE SORTIE
	# -------------------
	# <bibl> <author>Whittaker, J.</author>   (<date>1991</date>).   <title level="a">Graphical Models in Applied Multivariate Statistics</title>.   <publisher>Chichester: Wiley</publisher>. </bibl>

	# <bibl> <author>Surajit Chaudhuri and Moshe Vardi</author>.  <title level="a">On the equivalence of recursive and nonrecursive data-log programs</title>.   In <title level="m">The Proceedings of the PODS-92</title>,   pages <biblScope type="pp">55-66</biblScope>,   <date>1992</date>. </bibl>

	
	# TODO: pour 'citations' ajouter aussi les non alignées != groups_by_xid comme pour l'autre
	
	# voilà fin mode 2
	sys.exit(0)

