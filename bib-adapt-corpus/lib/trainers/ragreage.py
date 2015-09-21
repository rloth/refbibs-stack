#! /usr/bin/python3
"""
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
      (2) link_txtlines_with_xbibs()    ===> sortie reference-segmenter
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

# TODO bug sur la valeur des readed_label quand il y en a: crochets échappés ?

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
from subprocess import check_output

# mes méthodes XML
import rag_xtools # str_escape, strip_inner_tags, glance_xbib, 
                  # simple_path, localname_of_tag

# mes procédures
import rag_procedures  # find_bib_zone, link_txtlines_with_xbibs

# --------------------------------------------------------
# --------------------------------------------------------
# my global CONSTANTS

# namespace
NSMAP = {'tei': "http://www.tei-c.org/ns/1.0"}

# sert pour recombiner des tokens séparés: par ex " " ou ""
BLANK = " "

# pour la tokenisation des lignes via re.findall
re_TOUS = re.compile(r'\w+|[^\w\s]')  # => limites: chaque \b et chaque cara isolé type ponct
re_CONTENUS = re.compile(r'\w+')
re_PONCT = re.compile(r'[^\w\s]')


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
		          -p ech/pdf/oup_Human_Molecular_Genetics_ddp278.pdf
		          -m [bibzone|biblines|bibfields|authornames]""",
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
		        {'bibzone', 'biblines', 'bibfields', 'authornames'}""",
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

def get_xreaded_label(xbibs):
	""" Takes an array of xml biblStruct elements
	    and reports their readed_label of 2 kinds: numbers and QName ids
	"""
	
	# our array length
	nxb = len(xbibs)
	
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
			
			# todo pour les cas comme "1.", "2." 
			# => re.search(r"([0-9]+)[^0-9]*$")
			#    avec match.group(1)
			
			if postfix_num_match:
				thisbib_no_str = postfix_num_match.group(0)
				thisbib_no_int = int(postfix_num_match.group(0))
			else:
				# rien trouvé pour le no: on mettra None dans xml_nos_map
				thisbib_no_str = None
				thisbib_no_int = None
		
		# les 2 cas restants: trouvé no sans id OU trouvé aucun
		else:
			thisbib_id = None
			thisbib_no_str = None
			thisbib_no_int = None
		
		# stockage des readed_label/bibids trouvés
		# -----------------------------------
		xml_ids_map[j] = thisbib_id
		xml_no_strs_map[j] = thisbib_no_str
		xml_no_ints_map[j] = thisbib_no_int
		

	# check consecutivity
	# (ce diagnostic pourrait aussi être fait dès la boucle) 
	flag_std_map = True # temporaire
	for j, no in enumerate(xml_no_ints_map):
		if (no is None) or (int(no) != j+1):
			flag_std_map = False
	
	
	return (xml_ids_map, xml_no_strs_map, xml_no_ints_map, flag_std_map)



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

def biblStruct_elts_to_match_tokens(xml_elements, model="bibfields", debug=0):
	""" Prepares search tokens for each field of a reference
	
	Convertit une branche XML (1 refbib) avec tous ses sous-éléments
	   en une liste de tokens matchables (instances de XTokinfo)
	   en une liste de tokens matchables (instances de XTokinfo)
	   (avec 2 tags src=xip,tgt=xop + 1 ou psieurs contenus=str + 1 re)
	   dont certains spécifiquement groupés pour le modèle crf citations
	
	Difficulté à voir: il peut y avoir plus de tokens que d'éléments xml
	   par ex: <biblScope unit="page" from="20" to="31" />
	   => donne 2 tokens "20" et "31"
	
	Les tags et la regexp du token sont stockés dans son instance
	   tag src => xpath d'origine simple, avec les éventuels attributs pertinents
	   tag tgt => le précédent traduit en markup simplifié via table tei:biblStruct => tei:bibl
	   regexp => match défini dans classe XToken
	"""
	
	toklist = []
	
	# pour se souvenir de la forme de la page de début si présente
	# (utile pour calculer les formes possibles de la page de fin)
	mem_fpp = None
	
	for xelt in xml_elements:
		base_path = rag_xtools.simple_path(xelt, relative_to = "biblStruct")
		
		loc_name = rag_xtools.localname_of_tag(xelt.tag)
		
		if debug >= 2:
			print("xelt2tok:", file=sys.stderr)
			print("\tbase_path   :", base_path, file=sys.stderr)
			print("\ttext content: '%s'" % xelt.text, file=sys.stderr)
		
		
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

		# cas particuliers *pagination* groupés
		##     soit 2 tokens dans les attributs
		elif loc_name == 'biblScope' and xelt.get('unit') in ['page','pp'] and "from" in xelt.attrib and "to" in xelt.attrib:
			
			fpp_str = xelt.get('from')
			mem_fpp = fpp_str
			tok1 = XTokinfo( s=fpp_str,
			   xip='%s[@unit="pp"]' % base_path)
			toklist.append(tok1)
			
			# dernière page : variantes ['1645', '45']
			lpp_str = xelt.get('to')
			all_alternatives = lpp_variants(lpp_str, context=fpp_str)
			tok2 = XTokinfo(s= all_alternatives,
			   xip='%s[@unit="pp"]' % base_path )
			toklist.append(tok2)
		
		
		# cas à memoize *pagination* page de début seule => variable
		elif loc_name == 'biblScope' and xelt.get('unit') in ['page','pp'] and "from" in xelt.attrib:
			# enregistrement
			fpp_str = xelt.text if xelt.text else xelt.get('from')
			mem_fpp = fpp_str
			# tokenisation standard
			tok = XTokinfo( s=fpp_str,
			              xip='%s[@unit="pp"]' % base_path )
			toklist.append(tok)
			# print('----\nxelt2tok:fpp "%s" %s' % (fpp_str, base_path), file=sys.stderr)
		
		# cas particuliers *pagination* page finale seule =+> variantes
		elif loc_name == 'biblScope' and xelt.get('unit') in ['page','pp'] and "to" in xelt.attrib:
			lpp_str = xelt.text if xelt.text else xelt.get('to')
			all_alternatives = lpp_variants(lpp_str, context=mem_fpp)
			tok = XTokinfo(s=all_alternatives, xip='%s[@unit="pp"]' % base_path )
			toklist.append(tok)
			# print("====\nXELT2TOK:lpp '%s':%s"%(lpp_str,all_alternatives), file=sys.stderr)
		
		# tous les autres biblScope (vol, iss...) pour préserver leur @unit
		elif loc_name == 'biblScope':
			my_unit = xelt.get('unit')
			tok = XTokinfo( s=xelt.text,
			              xip='%s[@unit="%s"]' % (base_path, my_unit) )
			toklist.append(tok)
			# print('----\nxelt2tok:%s[@unit="%s"]' % (base_path, my_unit), file=sys.stderr)

		# les title avec leur @level
		# NB : xelt.text is not None devrait aller de soi et pourtant... pub2tei
		elif loc_name == 'title' and xelt.text is not None:
			this_level = xelt.get('level')
			if this_level == None:
				this_level="___"
			tok = XTokinfo( s=xelt.text,
			              xip='%s[@level="%s"]' % (base_path, this_level))
			toklist.append(tok)
		
		
		elif model != 'authornames' and loc_name in ['author','editor']:
			# les noms/prénoms à prendre ensemble quand c'est possible...
			#    pour cela on les traite non pas dans les enfants feuilles
			#    mais le + haut possible ici à (analytic|monogr)/(author|editor)
				subelts_str_list = [s for s in xelt.itertext()]
				all_orders_str_list = []
				for substr_combi in permutations(subelts_str_list):
					str_combi = BLANK.join(substr_combi)
					all_orders_str_list.append(str_combi)
				
				# du coup XTokinfo passe en multimode préparé ici
				# (ie l'arg s du token est différent: str[] et pas str)
				nametok = XTokinfo( s=all_orders_str_list,   # <----- ici liste
								  xip=base_path)
				toklist.append(nametok)

		# et du coup on ne re-traite pas tous les enfants du précédent
		elif model != 'authornames' and re.search(r'(?:author|editor)/.', base_path):
				continue

		# normalement on a déjà traité tous les cas avec texte vide et
		# ayant un attribut intéressant => ne reste que des "texte vide inintéressants"
		elif xelt.text is None:
			if debug >= 3:
				print ("xelt2tok: skip non terminal <%s>:'%s'"%(base_path, xelt.text), file=sys.stderr)
			continue

		# cas très rare d'un texte non vide mais non intéressant
		# ex: <publisher>&#x3000;</publisher> 
		#     trouvé dans els-0204CEAD3C2FF062A7EB4E8E2906925EFFB54CE2
		elif re.match("\u3000", xelt.text, re.UNICODE):
			if debug >= 3:
				print ("xelt2tok: skip terminal texte quasi vide <%s>:'%s'"%(base_path, xelt.text), file=sys.stderr)
			continue

		# === cas normal === (enfin !)
		# NB : noms/prénoms ajoutés au cas normal
		else:
			tok = XTokinfo(s=xelt.text, xip=base_path)
			toklist.append(tok)
			# print("====\nXELT2TOK:normal '%s'"%base_path, file=sys.stderr)
	
	
	# our XTokinfo array
	return toklist


def lpp_variants(lpp_str, context):
	""" Construit une  chaîne variante "aphérèse"
	    pour les éléments LAST PAGE.
	    
	    context: la 1ère page (pour faire le diff)
	    
	    ex: ['1245','245'] <= lpp_variants("1245", context="1120")
	    ex: ['1245','45']  <= lpp_variants("1245", context="1200")
	    
	    Prévu pour alimenter en "multimode" un attribut s=str[] pour un XTokinfo.
	"""
	n_chars = len(lpp_str)
	
	# on a toujours au moins la chaîne complète dans les matchables
	suffixes = [lpp_str]
	
	if context and (len(context) == n_chars):
		# sous-chaine commune
		k_common_chars = 0
		for i in range(0,n_chars):
			if lpp_str[i] == context[i]:
				k_common_chars += 1
		
		if k_common_chars != 0:
			# génération d'un seul suffixe de la bonne longueur
			suffixes.append(lpp_str[k_common_chars : n_chars])
	
	# pas de contexte connu => on tente toutes les aphérèses possibles
	else:
		for i in range(1,n_chars):
			#                       fin--        fin
			suffixes.append(lpp_str[n_chars-i : n_chars])
	
	# print('--------(ctxt:%s, lpp:%s => suff:%s)--------'%(context,lpp_str,suffixes), file=sys.stderr)
	
	# valeurs à renvoyer [lpp_str, variante_calculée]
	return suffixes


def reintegrate_matches(match_array, remainder_str):
	""" Réintègre des matchs transformés (chaine capturée, échappée, balisée)
	    dans leur chaîne originale, via des renvois de la forme:
	      #(#3-tit#)#
	    
	    (3ème match, de type titre)
	    
	    see also tok_match_record() for the reverse operation
	"""
	work_str = remainder_str
	
	for (k, rendu) in enumerate(match_array):
		renvoi = "#\(#%i-[a-z]+#\)#" % (k + 1)
		# ==================================
		work_str = re.sub(renvoi, rendu, work_str)
	
	return work_str


def tok_match_record(matchlist, remainder_str, xtoken, matched_substr):
	"""When an xml token matched a pdf substr, it
	   is recorded by this function in the 'matchlist'
	   
	   It is also removed from the original pdf string 
	   (and replaced by a ref of the form: "#(#1-reftype#)#"
	   for further tok <=> substr matches.
	   
	   Returns the updated list of substrings + the remainder
	   
	   see also reintegrate_matches() for the reverse operation
	   
	"""
	pstr_infostr = matched_substr
	xtok_infostr = re.sub(r'<([^<>"]{1,3})\w*(?: \w+="([^<>"]{1,3})\w*")?>',
	                     r'\1',
	                    xtoken.tagout)
	# print("SAVE p-substr:'%s' =~ m/%s/ix" % (pstr_infostr,xtok_infostr),file=sys.stderr)
	
	# -a- préparation du substitut balisé en xml
	#      £ pseudo_out == 'rendu'
	# debg
	pseudo_out = xtoken.tagout+rag_xtools.str_escape(matched_substr)+xtoken.endout
	
	# -b- enregistrement
	matchlist.append(pseudo_out)
	i = len(matchlist)
	
	# -c- effacement dans le remainder
	# (substitution par un renvoi à la \4 ex: #(#4#)#)
	# £todo!!! : interdire matches dans les renvois précédents (exemple n° volume == n° de renvoi) !
	remainder_str = re.sub(xtoken.re, "#(#%i-%s#)#" % (i, xtok_infostr), remainder_str)
	
	return(matchlist, remainder_str)



# NB ici model_type est utilisé seulement dans le cas label
def match_fields(grouped_raw_lines, subtrees=None, label="", model_type='bibfields', do_mask=False, 
                      debug_lvl=0):
	"""Matches field info in raw txt string
	   returns(output_xml_string, success_bool)
	   
	   Re-annotate all subelements in subtree this_xbib on
	   a slightly different textstream than the original xml
	   
	   (Minimal: re-annotate only label)
	   
	   (Use case: report des tags <bibl> sur une refbib training)
	
	   TODO cohérence arguments -m "citations" et -r
	
	Séquence :      FLUXTEXTE            XMLNODES
	               grouped_raw         list(subtrees) (ou xlabel seul)
	                    |                 |
	                    |               (iter)
	                    |                 |
	                    |             @subelts {xip, xtxt}+
	                    |                 |
	                    |                 |->  biblStruct_elts_to_match_tokens
	                    |                   [cas normal: un tag profond + contenu 
	                    |                                   => un markup plat à retrouver]
	                    |                   [gère aussi les cas où txt/tag découpés bizarrement]
	                    |                        -> prepare /xregex/
	                    |                        -> prepare <xop> (output tag)
	                    |                                  |
	                    |                  ============== /
	                    |             (XTok.init)
	                    |                 |
	                    |                 |                  -----
	                    |              @xtoklist {xip, xtxt, /xre/, <xop>}+
	                    |                 |                  -----
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
	if subtrees is None and label == "":
		raise ValueError("match_fields()"
		 +" il faut au moins un label ou une branche XML à reporter")
	elif subtrees is None:
		just_label = True
	else:
		just_label = False
	
	# - log -
	if debug_lvl >= 2 :
		print("MATCH_FIELDS:"+"="*50, file=sys.stderr)
		
		# rappel input XML
		if subtrees is not None:
			nxt = len(subtrees)
			print("match_fields: got %i subtree%s to match" % (nxt, 's' if nxt>1 else ''), file=sys.stderr)
			for subtree in subtrees:
				xmlentry = rag_xtools.glance_xbib(subtree)
				print("XML entry:", xmlentry
				   + "\ncontenus texte xmlbib", file=sys.stderr)
				# affiche élément XML pretty
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
		# print ("cherchons le label %s avec la toklist %s" % (label,toklist))
	
	# sinon tous les autres tokens:
	else:
		# £TODO éventuellement transformer biblStruct_elts_to_match_tokens
		#       pour qu'elle gère directement les subtree => lui permettrait de contrôler le parse
		#       par exemple quand on rencontre <author> et qu'on doit décider si on va + profond... ?
		
		# NB on ne prend pas le label qui n'est pas concerné par citations
		# mais on pourrait (en reprenant le début de liste du cas préc.) 
		# si on voulait faire un mode 'match intégral' (zone + ligne + label + fields + auteurs)
		
		# parcours de l'arbre
		# -------------------
		# on utilise iter() et pas itertext() qui ne donnerait pas les chemins!
		# + on le fait sous la forme iter(tag=elt) pour avoir les éléments
		#   et pas les commentaires
		subelts = []
		for subtree in subtrees:
			for xelt_s in subtree.iter(tag=etree.Element):
				subelts.append(xelt_s)
		
		# la boucle part des éléments xml (contenus attendus) pour
		# créer une liste de tokens avec à réintégrer à l'autre flux:
		#   - les contenus => point d'ancrage qui dira *où* réintégrer
		#                  => génère une expression régulière à trouver
		#   - leur balise  => décrit *ce que* l'on va réintégrer comme infos
		#                  => obtenue par table corresp selon relpath actuel
		
		# - - - - - - -
		# ON/ methode 1 : (appel fonction de correspondance cas par cas)
		#                 Crée objets "xtoken" avec qqs règles ad hoc:
		#                  - traduction de tags ad hoc pour les bibl
		#                  - récup texte d'attrs au lieu de contenus
		toklist += biblStruct_elts_to_match_tokens(
		                   subelts, 
		                     model=model_type, 
		                       debug=debug_lvl)
		
		# - - - - - - -
		# OFF/ méthode 2 générique (remettra tj le même tag qu'en entrée)
		#~ toklist = [XTokinfo(
					  #~ s=xelt.text,
					  #~ xip=rag_xtools.simple_path(
					  #~    xelt, 
					  #~    relative_to = rag_xtools.localname_of_tag(subtree.tag)
					  #~    )
					  #~ ) for xelt in subelts if xelt.text not in [None, ""]]
		
		if debug_lvl >= 1:
			print("\nTOKLIST", toklist, file=sys.stderr)
	
	
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
		if debug_lvl >= 3:
			print("xtok",l,tok, file=sys.stderr)
		
		# sanity check A : the xmlstr we just found
		if tok.xtexts is None:
			print("ERR: no xmlstr for %s" % tok.relpath, file=sys.stderr)
			unrecognized = True
			continue
		
		# print("RAW: {'%s'}" % remainder)
		
		# --------------------------------------------------------------
		# 3) on matche ------------------------------------------------|
		#  £TODO ?procéder par ordre inverse de longueur (mais \b)     |
		# ------------------------------------------------------------ |
		mtuples= re.findall( tok.re,  remainder )    #   <<== MATCH    |
		#                                                              |
		#  2 possibilités capture: en début ligne ou dans le milieu    |
		#        mais alors pas à l'intérieur des renvois #(#..#)#     |
		#   ==> tuples à 2 valeurs dont 1 vide == '' que l'on vire     |
		mgroups= [st for tup in mtuples for st in tup if st != '']    #|
		# print("===mgroups==>", mgroups, file=sys.stderr)            #|
		# -------------------------------------------------------------|
		n_matchs = len(mgroups)                                       #|
		# --------------------------------------------------------------
		
		#debg
		if debug_lvl >= 3:
			print ("\t%i match" % n_matchs, "(req)" if tok.req else "", file=sys.stderr)
		
		# 4) on traite le succès ou non du match -----------------  
		
		# si pas de match => :(
		if n_matchs < 1:
			if tok.req:
				# problème
				unrecognized = True
			if debug_lvl >= 2:
				print("WARN: no raw match for XToken '%s' (%s) aka re /%s/ (required = %s)" %
						 (tok.xtexts, tok.relpath, tok.re.pattern, tok.req),
						 file=sys.stderr)
			continue
		
		# si "beaucoup trop" de matchs => :(
		elif n_matchs > 2:
			if tok.req:
				unrecognized = True
				if debug >= 2:
					print("WARN: '%s' (%s) matches too many times (x%i)" %
							 (tok.xtexts, tok.relpath, n_matchs),
							 file=sys.stderr) 
			
			continue
		
		# si deux matchs => :/       (ex: volume or label?)
		# we choose arbitrarily one of the 2 matches TODO better
		elif n_matchs == 2:
			if debug_lvl >= 1:
				print("WARN: '%s' (%s) matched twice => choosing randomly" %
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
			if debug_lvl >= 1 :
				# au passage stat comparaison facultative:
				# chaines à erreurs OCR <=> chaines corrigées
				if tok.multimode == False and le_match != tok.xtexts:
					if re.sub('[- ¤]','',le_match) == re.sub('[- ¤]','',tok.xtexts):
						print("MATCH interpolé espaces, tirets et/ou sauts de lignes:\n\tPDF:'%s'\n\tXML:'%s'" 
								 % (le_match, tok.xtexts),
							  file=sys.stderr)
					elif le_match.lower() == tok.xtexts.lower():
						print("MATCH interpolé casse:\n\tPDF:'%s'\n\tXML:'%s'" 
								 % (le_match, tok.xtexts),
							  file=sys.stderr)
					else:
						print("MATCH interpolé autres (OCR?):\n\tPDF:'%s'\n\tXML:'%s'" 
								 % (le_match, tok.xtexts),
							  file=sys.stderr)
			# ----------------------------------8<----------------------
		
		# fins cas de figures match
	# fin boucle sur tokens
	
	# print("$remainder:", remainder, file=sys.stderr)
	# print("@mtched   :", mtched, file=sys.stderr)
	
	# traitement du remainder => résultat visible avec option -r (mask)
	remainder = rag_xtools.str_escape(remainder)
	
	# SORTIE (str)
	new_xml = None
	
	# si l'utilisateur ne veut que le masque 
	# (aka remainder : tout sauf les matchs, sans post-traitements)
	if do_mask:
		new_xml = remainder
	
	# sinon cas normal
	else:
		# réinsertion ch. match interpolé de subtrees IN
		#  ==> (chaîne verbatim re-balisée, xmlescaped)
		# ----------------------------------------------
		output = reintegrate_matches(mtched, remainder)
		# ----------------------------------------------
		
		#~ print ("output:", output, file=sys.stderr)
		
		
		# PUIS:
		# post-traitements selon les cas de sortie voulue
		# ----------------
		# cas 1 : si mode label seul (quelquesoit le model_type courant)
		if just_label:
			# les readed_label sont souvents des attributs n=int mais
			# dans le corpus d'entraînement on les balise avec leur ponct
			# ex: "[<label>1</label>]"  ==> "<label>[1]</label>"
			new_xml = re.sub("\[<label>(.*?)</label>\]",
						   "<label>\[\1\]</label>",
						   output)
		
		# cas 2 : sélection de la partie auteurs seule
		elif model_type == "authornames":
			au_str = None
			# cette version marche uniquement par regexp sur *names...
			# £TODO utiliser plutôt les 2 niveaux de markup
			#                       (tei:author et tei:*names)
			# car problèmes actuels comme :
			#   <authors><lastname>World Bank</lastname>. Accelerated
			#   development in sub-Saharan Africa: An agenda for <lb/>
			#   action. Washington DC, <lastname>World Bank</lastname>
			#   </authors>
			
			if unrecognized:
				au_str = "" # <= on n'a rien trouvé
			else:
				# selection du segment MAXIMAL contenant les noms
				# £TODO éviter les chaînes intercalées trop longues ?
				got = re.match(r"[^<>]*(<\w*name>.*</\w*name>)[^<>]", output)
				
				#~ version avec trailing punctuations
				#~ r"[^<>]*(<\w*name>.*</\w*name>)[^<>]\W*"
				
				
				# pas de capture => anormal
				if got is None:
					# on annule le succès
					unrecognized = True
					# on signale le problème
					print("WW: no names in '%s'" % au_str, file=sys.stderr)
					au_str = "" # <= on a rien trouvé
				# cas normal
				else:
					au_str = got.groups()[0]
			
			# ajout tag extérieur
			# -------------------
			new_xml = "<authors>"+au_str+"</authors>"   # ?TODO editors idem ?
		
		# cas 3 : bibfields (modèle grobid = "citations")
		elif model_type == "bibfields":
			
			# correctif label  => TODO à part dans une matcheuse que pour label?
			# ---------------
			#   Les readed_label sont souvents des attributs n=int mais
			#   dans le corpus d'entraînement on les balise avec leur ponct
			#   ex: [<label>1</label>]  ==> <label>[1]</label>
			output = re.sub("\[<label>(.*?)</label>\]",
								 "<label>[\g<1>]</label>",
								   output)
			
			# dernier correctif: groupements de tags
			# ------------------
			
			# -a- pages collées si possible pour le modèle citation
			#                   grace astuce amont: marquage tempo <pp>
			output = re.sub(r'<pp>', r'<biblScope type="pp">',
					  re.sub(r'</pp>', r'</biblScope>',
					 re.sub(r'(<pp>.*</pp>)',rag_xtools.strip_inner_tags,
					output)))
			
			# -b- auteurs groupés
			# ex <author>Ageta, H.</author>, <author>Arai, Y.</author> 
			#        => <author>Ageta, H., Arai, Y.</author>
			output = re.sub(r'(<author>.*</author>)',
								  rag_xtools.strip_inner_tags, 
								output)
			output = re.sub(r'(<editor>.*</editor>)',
								  rag_xtools.strip_inner_tags,
								output)
			
			# ajout tag extérieur
			# -------------------
			new_xml = "<bibl>"+output+"</bibl>"
	
	
	
	return(new_xml, not(unrecognized))
	# autrement dit ==> (new_xml, success_bool)


# --------------------------------------------------------
# --------------------------------------------------------


class XTokinfo:
	"""Groups infos about a str token found in the source XML"""
	# pour matcher malgré des erreurs OCR
	OCR_SIMILAR_CHARACTER = {
	  '0' : ['0', 'O'],
	  '1' : ['1', 'l', 'I'],
	  '2' : ['2', 'E'],
	  '5' : ['S', '5'],
	  '8' : ['8', 'B'],
	  'a' : ['a', 'u', 'n'],
	  'b' : ['b', 'h'],
	  'ä' : ['ä', 'a', 'g', 'L'],
	  'c' : ['c', 'e', 't'],
	  'ç' : ['ç', 'q'],
	  'd' : ['d', 'cl'],
	  'e' : ['e', 'c', '¢'],
	  'é' : ['é', '6', 'e', 'd', '~'],
	  'è' : ['è', 'e', 'Q'],
	  'f' : ['f', 't'],
	  'h' : ['h', 'b'],
	  'i' : ['i', ';', 'l'],
	  'l' : ['1', 'l', 'i','I', ']', '/', 'Z'],
	  'm' : ['m', 'rn', 'nn', 'ni'],#commentfairelesrèglesinverses 2->1 :/ ?
	  'n' : ['n', 'rt', 'll'],
	  'o' : ['o', 'c'],
	  'ø' : ['ø', 'o'],
	  'ö' : ['ö', 'o', '6', 'S', 'b', '~'],
	  't' : ['t', 'f', '¹', 'r'],
	  'ü' : ['ü', 'u', 'ii', 'ti', 'fi'],
	  'v' : ['v', 'y'],
	  'y' : ['y', 'v'],
	  'B' : ['B', '8'],
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
	
	  #~ '.' : ['.', ','],       # risque d'attraper un séparateur en trop
	  '·' : ['.', '·'],
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
	  'analytic/title[@level="a"]' :                      '<title level="a">',
	  'analytic/title/hi' :                               '__rmtag__',  # todo effacer le tag
	  'analytic/title/title/hi' :                         '__rmtag__',
	  'analytic/translated-title/maintitle':              '<note>',     # pour CRF
	  'analytic/author/persName/surname' :                '<lastname>',
	  'analytic/author/persName/forename':                '<forename>',
	  'analytic/author/persName/forename[@type="first"]': '<forename>',
	  'analytic/author/persName/forename[@type="???"]':   '<middlename>',
	  'analytic/author/persName/genName':                 '<suffix>',
	  'analytic/author/forename' :                        '<forename>',
	  'analytic/author/surname' :                         '<lastname>',
	  'analytic/author/orgName' :                         '<author>',  # ? orgName en <bibl> ?
	  'analytic/author' :                                 '<author>',
	  'analytic/name' :                                   '<author>',  # wtf?
	  'analytic/respStmt/name' :                          '<author>',
	  'monogr/author/persName/surname' :                  '<lastname>',  # <!-- monogr -->
	  'monogr/author/persName/forename' :                 '<forename>',
	  'monogr/author/persName/forename[@type="first"]' :  '<forename>',
	  'monogr/author/persName/forename[@type="???"]' :    '<middlename>',
	  'monogr/author/persName/genName' :                  '<suffix>',
	  'monogr/author/orgName' :                           '<author>',  # ? orgName en <bibl> ?
	  'monogr/author' :                                   '<author>',
	  'monogr/respStmt/name' :                            '<author>',
	  'monogr/imprint/meeting' :                  '<title level="m">',
	  'monogr/meeting' :                          '<title level="m">',
	  'monogr/imprint/date' :                     '<date>',
	  'monogr/imprint/date/@when' :               '<date>',
	  'monogr/title[@level="j"]' :                '<title level="j">',
	  'monogr/title[@level="m"]' :                '<title level="m">',
	  'monogr/imprint/title[@level=""]' :         '<title level="m">',  # wtf ?
	  'monogr/imprint/biblScope[@unit="vol"]' :      '<biblScope type="vol">',
	  'monogr/imprint/biblScope[@unit="issue"]':     '<biblScope type="issue">',
	  'monogr/imprint/biblScope[@unit="part"]' :     '<biblScope type="chapter">',
	  'monogr/imprint/biblScope[@unit="chap"]' :     '<biblScope type="chapter">',
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
	  'analytic/idno' :                     '<idno>',
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
			self.multimode = False
		
		# -b- 
		# 1 token = k strings as alternatives
		# initialisation combinée avec une liste str DIY
		# (ex: self.xtexts = ["124-128", "124-28", "124-8"])
		# (ex: self.xtexts = ["NomBLANKPrénom", "PrénomBLANKNom"])
		elif type(s) == list:
			self.xtexts = s
			self.multimode = True
		
		else:
			raise TypeError(type(s), "str or str[] expected for newtok.s at %s" % self.relpath)
		
		# <<  "isRequired" BOOL
		#    (ex: label not required)
		# /!\ most tokens are required for successful align
		self.req = req
		
		# 2) on prépare des expressions régulières pour le contenu
		# ---------------------------------------------------------
		# <> SELF.RE
		#  ex: "J Appl Phys" ==> r'J(\W+)Appl(\W+)Phys'
		#  si tiret autorisé encore + complexe:
		#               ==> r'(?=^.{11,15}$)J(\W+)A[-¤]{0,2}p[-¤]{0,2}p[-¤]\ #
		#                     {0,2}l(\W+)P[-¤]{0,2}h[-¤]{0,2}y[-¤]{0,2}s'
		# => les chaînes "multimode" seront matchables dans les 2 ordres possibles
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
	def str_pre_regexp(self, anystring, debug_lvl = 0):
		""""Just" the raw regexp string to use later within captures etc
		     |
		     |-> escaped
		     |-> potential extra spaces
		     |-> potential hyphens
		     |-> potential newlines
		     |-> with interpolated ocr-variants via char classes
		"""
		
		strlen = len(anystring)
		
		# A) préparation du contenu
		# --------------------------
		subtokens = re_TOUS.findall(anystring)
		
		# £TODO use those params below in r_INTER_*
		do_cesure=True
		do_espace=True
		do_newline=True
		do_char_classes=True
		
		# autorise saut de ligne, espace et toutes poncts
		# (ex: ',' entre nom et prénom)     -------------
		r_INTER_WORD = '[¤ \W]{0,4}'
		
		# autorise césure, saut de ligne, espace
		r_INTER_CHAR = '[-¤ ]{0,3}'
		
		# on ne fait pas la césure pour les locutions courtes
		if (not do_cesure or strlen < 6):
			# re: chaîne de base 
			# ------------------
			# autorisant un ou des passage-s à la ligne à chaque limite 
			# limites selon re_FINDALL = (\b et/ou bords de ch. ponct)
			my_re_str = r_INTER_WORD.join(r"%s" % re.escape(u) for u in subtokens)
		
		# expression + sioux pour permettre césure inattendue et erreurs OCR
		else:
			minlen = strlen
			# on permet 3 caractères en plus tous les 80 caractères
			maxlen = strlen + ((strlen // 80)+1) * 3
			
			# lookahead sur /./ ==> exprime la contrainte de longueur de la regex qui suivra
			re_length_prefix = r"(?=.{%i,%i})" % (minlen, maxlen)
			
			interpolated_tokens = []
			
			# interpolations dans chaque token...
			for u in subtokens:
				interpold_word=""
				array_c_re = []
				
				# ... donc pour chaque **caractère**
				#          =========================
				for c in u:
					# each character regexp
					c_re = ""
					
					# cas simple sans traitement OCR
					# ----------
					if not do_char_classes or (c not in XTokinfo.OCR_CLASSES):
						# esc !
						c_re = re.escape(c)
						
						# store
						array_c_re.append(c_re)
					
					# cas avec OCR: sub/caractère/groupe de caractères 'semblables'/g
					# -------------
					else:
						c_matchables = XTokinfo.OCR_SIMILAR_CHARACTER[c]
						# esc + joined alternatives
						c_alter = '|'.join(map(re.escape,c_matchables))
						
						# ex : regexp = '(?:i|l)'
						c_re += '(?:' + c_alter + ')'
						
						# store
						array_c_re.append(c_re)
					
					# dans les 2 cas: césure
					# ----------------------
					# on va ajouter /-?/ entre ch. "regexp caractère" (ou re_INTER_CHAR)
					interpold_word = r_INTER_CHAR.join(array_c_re)
				
				interpolated_tokens.append(interpold_word)
				
				my_re_str = re_length_prefix + r_INTER_WORD.join(r"%s" % u 
				                       for u in interpolated_tokens)
				
				# exemple
				# ====x_str==== Oxidation of Metals
				# ====re_str==== (?=.{19,22})(?:O|0))[-¤ ]{0,3}x[-¤ ]{0,3}(?:i|\;|l)[-¤ ]{0,3}(?:d|cl)[-¤ ]{0,3}(?:a|u|n)[-¤ ]{0,3}t[-¤ ]{0,3}(?:i|\;|l)[-¤ ]{0,3}(?:o|c)[-¤ ]{0,3}n[¤ ]{0,2}(?:o|c)[-¤ ]{0,3}(?:f|t)[¤ ]{0,2}M[-¤ ]{0,3}(?:e|c)[-¤ ]{0,3}t[-¤ ]{0,3}(?:a|u|n)[-¤ ]{0,3}(?:1|l|i|I|\]|\/|Z)[-¤ ]{0,3}s
			
		
		
		if debug_lvl >= 2 :
			print("SUBTOKS", subtokens)
		
		if debug_lvl >= 3 :
			print("pre_regexp:", file=sys.stderr)
			print("\t=x_str=", anystring, file=sys.stderr)
			print("\t=re_str=", my_re_str, file=sys.stderr)
		
		
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
	def tok_full_regexp(self, case=False):
		"""The precompiled regexp with alternatives and parentheses around"""
		re_str=""
		
		# => cas normal : une seule chaîne dans self.xtexts
		if not self.multimode:
			# récup d'une seule chaîne échappée
			re_str = self.str_pre_regexp(self.xtexts)
		
		# => plusieurs chaînes matchables à alimenter avec:
		#   - permuts de 2 elts + BLANK (DIY) quand
		#     les XML  n'ont pas préservé l'ordre
		#   - listes de possibilité (à préparer avant)
		#     quand variantes multiples
		elif self.multimode:
			alternatives = []
			# ex: ['nom prénom', 'prénom nom'] => /((?:nom\W*prénom)|(?:prénom\W*nom))/
			# ex: ['PP1-PP2', 'PP1-P2', 'PP1-2'] => /((?:PP1-PP2)|(?:PP1-P2)|(?:PP1-2))/
			for single_text in self.xtexts:
				# pre_regexp ajoute les interpolations
				# INTERWORD et INTERCHAR pour ch. chaîne
				re_single = self.str_pre_regexp(single_text)
				
				# capsule "non capturing"
				alternatives.append("(?:"+re_single+")")
			
			# combi1 -OR- combi2... (using regex pipe)
			re_str = "|".join(alternatives)
		
		# enfin ajout de balises de capture extérieures
		# et compilation (en case insensitive sauf exceptions)
		# -----------------------------------------------------
		#  2 possibilités capture: en début ligne ou dans le milieu
		#        mais alors pas à l'intérieur des renvois #(#..#)#
		if not case:
			my_regexp_object = re.compile("(?:^("+re_str+"))|(?:(?<!#\(#)("+re_str+"))", re.IGNORECASE)
		else:
			my_regexp_object = re.compile("(?:^("+re_str+"))|(?:(?<!#\(#)("+re_str+"))")
		return my_regexp_object
	
	
	def __str__(self):
		return "%s: '%s'" % (self.tagout, self.xtexts)
	
	def __repr__(self):
		return "<%s>" % self.__str__()

# --------------------------------------------------------

def run(the_model_type = "bibzone",
		the_pdfin  = None ,        # chemin fichier PDF
		the_txtin  = None ,        # chemin fichier TXT
		the_xmlin  = None ,        # chemin fichier XML
		do_mask    = False,
		checklist  = [True, True, True],
		debug_lvl = 0
		):
	"""
	Full run mis dans une fonction pour appel plus commode.
	
	Lancé avec les arguments cli en tant qu'objet argparse
	(cf. leur définition tout en bas de ce fichier)
	
	Sortie anciennement "stdout" renvoyée sur yield pour 
	impression par le main ou par toute fonction appelante.
	"""
	
	# each diagnostic whether the xml:ids end with 1,2,3... 
	# (TODO: autres diagnostics :
	#     -> absents, non numériques, consécutifs avec début != 1 etc)
	flag_std_map = False

	# said endings 1,2,3 (if present) for label retrieval
	# utilise l'attribut "n" quand il est présent
	# (dans la feuille elsevier il reprenait value-of sb:label)

	readed_label = []
	
	
	#    INPUT XML
	# ================
	print("LECTURE XML %s" % the_xmlin, file=sys.stderr)

	parser = etree.XMLParser(remove_blank_text=True)
	
	# parse parse
	try:
		dom = etree.parse(the_xmlin, parser)

	except OSError as e:
		print(e, file=sys.stderr)
		return None

	except etree.XMLSyntaxError as e:
		print("RAG xml input error: %s %s (skip)" % (the_xmlin, e),
		                        file=sys.stderr)
		return None

	# stockage DOCID
	DOCID = "RAG-"+re.sub( "\.xml$", # sans suffixe
					"",
					# sans dossiers
					re.sub("^.*/([^/]+)$", r"\1", the_xmlin)
				   )

	# query query
	xbibs = dom.findall(
				"tei:text/tei:back//tei:listBibl/tei:biblStruct",
				namespaces=NSMAP
				)

	# toutes les bibls ou biblStruct
	xbibs_plus = dom.xpath(
				"tei:text/tei:back//tei:listBibl/*[local-name()='bibl' or local-name()='biblStruct']",
				 namespaces=NSMAP
				)

	# nombre de xbibs traitables si bibfields ou names
	nxb = len(xbibs)

	# nombre de xbibs traitables si biblines ou bibzone
	nxb_plus = len(xbibs_plus)

	# pour logs
	nxbof = nxb_plus - nxb

	# prise en compte <bibl>+<biblStruct> ou <biblStruct> ?
	if the_model_type in ["bibzone", "biblines"]:
		print ("N xbibs: %i" % nxb_plus, file=sys.stderr)
		# plus besoin de maintenir la différence entre les 2 ensembles
		xbibs = xbibs_plus
		nxb = nxb_plus
		
		# exception critique si aucune bib
		if (nxb == 0):
			print("ERR: aucune xbib <bibl> ni <biblStruct> dans ce xml natif !",
					 file=sys.stderr)
			return None

	else:
		print ("N xbibs: %i" % nxb, file=sys.stderr)
		
		# £TODO ICI cas (bibfields ou authors) MAIS avec special bibl Nature|Wiley
		
		# si présence de <bibl>
		if (nxbof > 0):
			print("WARN: %i entrées dont  %i <bibl> (non traitées)" %
					 (nxb_plus, nxbof),
					 file=sys.stderr )
			
			# incomplétude du résultat à l'étape 0
			checklist[0] = False
			
			
			# TODO : traiter les <bibl> ssi sortie refseg 
			# + les prendre en compte dans le décompte de enumerate(xbibs)

		# exception critique si aucune <biblStruct>
		if (nxb == 0):
			print("ERR: aucune xbib <biblStruct> dans ce xml natif !",
					 file=sys.stderr)
			return None


	# préalable: passage en revue des XML ~> diagnostics IDs
	# ----------
	(xml_ids_map,         # ex: ['BIB1', 'BIB2', ...] 
						  # ou: ['pscr214821bib1', 'pscr214821bib2', ...]
	 xml_no_strs_map,     # ex: ['1.', '2.', ...] ou ['[1]', '[2]', ...]
	 xml_no_ints_map,     # ex:  [1, 2, ...]
	 flag_std_map         # ex:  True (si consécutifs)
	 ) = get_xreaded_label(xbibs)

	# écriture dans variable globale pour matcher les readed_label réels en sortie
	# £TODO : sauter les <bibl> et garder uniquement les biblStruct sinon 
	#         indices décalés => IndexError "list index out of range"
	for item in xml_no_strs_map:
		if item is None:
			readed_label.append(None)
		else:
			# remove padding 0s
			no = re.sub("^0+", "", item)
			readed_label.append(no)


	if debug_lvl >= 1:
		print("IDs:", xml_ids_map, file=sys.stderr)
		if debug_lvl >= 2:
			print("NOs:", xml_no_ints_map, file=sys.stderr)
			print("NO_strs:", xml_no_strs_map, file=sys.stderr)
			if flag_std_map:
				print("GOOD: numérotation ID <> LABEL traditionnelle",
						 file=sys.stderr)
			else:
				# todo préciser le type de lacune observée :
				# (pas du tout de readed_label, ID avec plusieurs ints, ou gap dans la seq)
				print("WARN: la numérotation XML:ID non incrémentale ou consécutive",
						 file=sys.stderr)

	# // fin lecture xml bibs


	if the_txtin:
		#  INPUT TXT à comparer
		# ======================
		print("---\nLECTURE FLUX TXT ISSU DE PDF", file=sys.stderr)
		
		try:
			rawlines = [line.rstrip('\n') for line in open(the_txtin)]
		except FileNotFoundError as e:
			print("I/O ERR: Echec ouverture du flux textin '%s': %s\n"
					  % (e.filename,e.strerror),
					  file=sys.stderr)
			return None

	elif the_pdfin:
		#  INPUT PDF à comparer
		# ======================
		print("---\nLECTURE PDF", file=sys.stderr)

		# appel pdftotext via OS
		try:
			pdftxt = check_output(['pdftotext', the_pdfin, '-']).decode("utf-8")
		
		except CalledProcessError as e:
			print("LIB ERR: Echec pdftotxt: cmdcall: '%s'\n  ==> failed (file not found?)" % e.cmd, file=sys.stderr)
			# print(e.output, file=sys.stderr)
			return None
		
		# we got our pdf text! -----------
		
		# remove form feed (page break marker)
		pdftxt= re.sub(r'\f', '\n', pdftxt)
		
		# split in lines
		rawlines = [line for line in pdftxt.split("\n")]

	else:
		print("""ARG ERR: On attend ici --pdfin foo.pdf
				 (ou alors --txtin bar.txt)""",
				 file=sys.stderr)
		return None


	# pour logs
	# ---------
	npl = len(rawlines)

	print ("N lignes: %i" % npl, file=sys.stderr)

	
	# """ coeur du main
	#     -------------
	#    on a un doc XML structuré et un PDF ou un texte issu de PDF non-structuré 
	#   (même objet doc mais avec des erreurs OCR et des virgules etc un peu différentes)
	# 
	#   le but est de recréer un "TRAIN.XML" d'entraînement de balisage
	#   qui reprend:
	#     - la structure du document XML en input
	#     - les contenus (chaînes de caractères) du flux texte du PDF
	# 
	# Les "train.xml" peuvent être de 3 types selon l'étape de balisage
	# de Grobid ou Cermine qu'on veut entraîner.
	# 
	#    >> train.segmentation.tei.xml          (--mode segmentation)
	#    >> train.referenceSegmenter.tei.xml    (--mode refseg)
	#    >> train.references.tei.xml            (--mode refs)
	# 
	# # pour le use case "segmentation" on veut la zone des refbibs
	# # pour le use case "refseg" on veut les lignes PDF de chaque refbib XML et les readed_label
	# # pour le use case "refs" on veut les champs dans chaque refbib
	# 
	# 
	# Ce main effectue un choix du mode et le lancement des sous-procédures
	# correspondantes.
	# """

	# La zone biblio dans le texte  pdf est un segment marqué par 2 bornes
	#       (par ex: d=60 et f=61 on aura |2| lignes intéressantes)
	#      par défaut elle est égale à toute la longueur du document
	# ----------------------------------------------------------------------
	debut_zone = 0
	fin_zone = npl - 1


	# -------==========----------------------------------------
	# boucle --mode seg (objectif: repérage macro zone de bibs)
	# -------==========----------------------------------------
	if the_model_type == "bibzone":
	# =======================
	#  Recherche zone biblio
	# =======================
		header="""<?xml version="1.0" encoding="UTF-8"?>
<tei type="grobid.train.segmentation">
	<teiHeader>
		<fileDesc xml:id="%s"/>
	</teiHeader>
	<text xml:lang="en">""" % DOCID
		yield (header)

		print("---\nFIND PDF BIB ZONE", file=sys.stderr)
		
		(debut_zone, fin_zone) = rag_procedures.find_bib_zone(
										 xbibs,
										 rawlines,
										 debug=debug_lvl
								  )
		
		#  !! debut_zone et fin_zone sont des bornes inclusives !!
		#  !!         donc nos slices utiliseront fin+1         !!
		#                      ------             -----
		
		
		# le matériau ligne par ligne échappé pour sortie XML seg
		esclines = [rag_xtools.str_escape(st) for st in rawlines]
		
		# rarement
		if ((debut_zone == None) or  (fin_zone == None)):
			print("ERR: trop difficile de trouver la zone biblio dans ce rawtexte '%s': je mets tout en <body>" % the_pdfin, file=sys.stderr)
			yield("\t\t<body>")
			yield("<lb/>".join(esclines[0:npl])+"<lb/>")
			yield("\t\t</body>")
		# cas normal
		else:
			# £TODO ajouter éventuellement quelquechose
			# pour générer des balises <page> et le <front>
			# (si l'entraînement se passe mal sans)
			
			
			yield("\t\t<body>")
			yield("<lb/>".join(esclines[0:debut_zone])+"<lb/>")
			yield("\t\t</body>")
			yield("\t\t<listBibl>")
			yield("<lb/>".join(esclines[debut_zone:fin_zone+1])+"<lb/>")
			yield("\t\t</listBibl>")
			if (fin_zone < npl-1):
				yield("\t\t<body>")
				yield("<lb/>".join(esclines[fin_zone+1:npl])+"<lb/>")
				yield("\t\t</body>")
		# tail
		tail="""
	</text>
</tei>"""
		yield (tail)


	# pour tous les autres modes: [biblines, bibfields, authornames]
	else:
		
		# un match de chaque ref XML vers PDF (pour aligner)
		# (commun au deux modes "refseg" et "cit")
		# =======================================
		#        link_txtlines_with_xbibs
		# =======================================
		print("---\nLINK PDF BIBS <=> XML BIBS", file=sys.stderr)



		# get correspondance array
		# (sequence over pdf content lines ids filled with matching xml ids)
		winners = rag_procedures.link_txtlines_with_xbibs(
						   rawlines[debut_zone:fin_zone+1], 
						   xbibs,    # todo check si les bibl passent bien ? 
						   debug=debug_lvl
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
		
		
		
		
		# -------====================---------------------------------
		# boucle OUTPUT --mode refseg (objectif: alignements de bibs)
		# -------====================---------------------------------
		#   Relier les bibs du texte brut (opaques) avec celles du xml (connues)
		#
		#   use case: création training.referenceSegmenter.tei.xml pour grobid
			
		if the_model_type == "biblines":
			
			# log de la checkliste (évaluation qualité de ce qui sort)
			# non nécessaire pour les citations (mis inline)
			CHECKS = open("checks.refseg.tab", "a")

			# header
			header="""<?xml version="1.0" encoding="UTF-8"?>
<tei type="grobid.train.refseg">
	<teiHeader>
		<fileDesc xml:id="%s"/>
	</teiHeader>
	<text xml:lang="en">
		<listBibl>""" % DOCID
			yield (header)
			
			# yalla !
			print ("~" * 80, file=sys.stderr)
			
			# line buffer (when several lines of the same xml elt)
			l_buff = []
			
			# txtin donc len(winners) = len(rawlines)
			if len(winners) != len(rawlines):
				raise ValueError("wtf??")
			
			
			# keep count of what we wrote
			n_wbibl = 0
			
			# ne pas oublier de rajouter un marqueur fin de lignes après ch. rawlines
			
			# £dbg
			print(readed_label)
			
			for i, this_line in enumerate(rawlines):
				
				# récup de l'indice XML correspondant à la ligne
				# NB les indices sont 0-based et les readed_label souvent 1-based
				j_win = winners[i]
				
				# lookahead de l'indice suivant
				if i+1 < npl:
					next_win = winners[i+1]
				else:
					next_win = None
				
				accumulated_buff_size = len(l_buff)
				if debug_lvl >= 3:
					print("-x-x-x-x-biblines-------------x-x-x-x-", file=sys.stderr)
					print("buffer accumulated size:", accumulated_buff_size, file=sys.stderr)
					print("j_win:", j_win, "next_win:", next_win, file=sys.stderr)
					print("label:", readed_label[j_win] if j_win is not None else "__no_label__", file=sys.stderr)
				
				
				
				# cas aucune ligne matchée
				if j_win is None:
					# on ne peut pas reporter "<bibl>...</bibl>" sur la ligne
					# mais on la sort quand même (fidélité au flux txtin)
					yield(rag_xtools.str_escape(this_line)+"<lb/>")
					#                  -------
					#                 important!
					
				else:
					# ------------------------------------------------------
					# 2 tests, 4 possibilités
					# -----------------------
					#                accumulated_buffer==0   j_win==next_win
					# 1 ligne seule       True                     False
					# ligne initiale      True                     True
					# ligne de contin.    False                    True
					# ligne de finbib     False                    False
					# ------------------------------------------------------
					# actions:
					# --------
					# si   acc_buff == 0  => préfixer avec "<bibl>"
					#                     => chercher label si xlabel
					#
					# si j_win==next_win  => accumuler >> buffer
					# si j_win!=next_win  => "<lb/>".joindre +"<lb/></bibl>"
					#                     => imprimer
					#                     => vider buffer
					# ------------------------------------------------------
					# nouveau morceau
					if accumulated_buff_size == 0:
						# tentative de report du label
						xlabel = readed_label[j_win]
						
						# ?TODO par ici :  possible de tester ce passage sur
						# des bibl trainerlike (sans ragreage, juste transfo)
						# en les comparant <note rend="LABEL"> <=> <label> => readed_label[j]
						
						if xlabel:
							# TODO faire une fonction à part et reserver
							# match_fields au cas citations ?
							# -------------------8<-------------------------
							# report label sur chaîne de caractères réelle
							(this_line_wlabel, success) = match_fields(
														this_line,
														label = xlabel,
														debug_lvl = debug_lvl -1,
														model_type = the_model_type
													   )
							# -------------------8<-------------------------
							
							my_bibl_line = '<bibl>'+this_line_wlabel
						else:
							my_bibl_line = '<bibl>'+ rag_xtools.str_escape(this_line)
						
						# to be continued
						if j_win == next_win:
							# >> BUFFER
							l_buff.append(my_bibl_line)
						
						# pas de morceau suivant (cas d'une ligne seule)
						else:
							my_bibl_line = my_bibl_line+'<lb/></bibl>'
							yield(my_bibl_line)
							n_wbibl += 1
							
					
					# morceaux de suite
					elif next_win == j_win:
						# ligne sans balises et sans sa fin
						# >> buffer
						l_buff.append(rag_xtools.str_escape(this_line))
					
					# morceau de fin => fermeture tag + jonction => SORTIE
					else:
						# separateur saut de ligne pour les lignes internes
						#  => sortie finale format ref-seg
						#     -------------
						preceding = '<lb/>'.join(l_buff)
						current_l =  rag_xtools.str_escape(this_line)
						yield(preceding+'<lb/>'+current_l+'<lb/></bibl>')
						#                ----             ------
						#                               fin de la
						#                             dernière ligne
						n_wbibl += 1
						# vider le buffer
						l_buff = []
					
					if debug_lvl >= 3:
						print('buffer', l_buff, file=sys.stderr)
			
			if debug_lvl >= 3:
				print("-x-x-x-x----------------------x-x-x-x-", file=sys.stderr)
			
			# post-diagnostic critique
			if nxb < n_wbibl:
				checklist[1] = False 
			
			# diagnostic
			diagno_refseg = str(int(checklist[0]))+str(int(checklist[1]))
			yield ("<!--diagno_biblines:"+ diagno_refseg +"-->")
			
			print ("~" * 80, file=sys.stderr)
			
			# tail
			tail="""
		</listBibl>
	</text>
</tei>"""
			yield (tail)
		
		
		
		# -------------------------------------------------------------
		#  mode 2: boucle plus simple pour la sortie refs (citations détaillées)
		# -------------------------------------------------------------
		#    in refs mode we go further by grouping content from pdf
		#     (each raw txtline i') by its associated xml id j_win
		#   --------------------------------------------------------
		elif the_model_type == "bibfields":
			
			header="""<?xml version="1.0" encoding="UTF-8"?>
<tei type="grobid.train.citations">
	<teiHeader>
		<fileDesc xml:id="%s"/>
	</teiHeader>
	<text xml:lang="en">
		<listBibl>""" % DOCID
			yield (header)
			
			print ("x" * 80, file=sys.stderr)
			
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
						#  conséquence sur format sortie dans les reports: 
						#        => NEUTRE car matche /\W+/
						rawlinegroups_by_xid[j_win] += "¤"+rawlines[debut_zone+i_prime]
			
			# log détaillé de cette étape
			if debug_lvl >= 3:
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
			
			# itération simultanée sur les xbibs et les rawlines qui leur ont été associées
			#             (index j => this_xbib)
			for j, group_of_real_lines in enumerate(rawlinegroups_by_xid):
					
					# la dernière est parfois vide
					if (group_of_real_lines is None) and (j == max_j):
						continue
					
					try:
						this_xbib = xbibs[j]
					except IndexError as ie:
						print("Bib j=%i absente dans xbibs pour '%s'" % 
									   ( j, 
										 group_of_real_lines ),
						file=sys.stderr)
						# on donne un biblStruct vide
						this_xbib = etree.Element('biblStruct', type="__xbib_non_listée__")
					
					# les indices sont ici les mêmes que ceux de xbibs
					xlabel = readed_label[j]
					
					toks = []
					
					if group_of_real_lines is None:
						if debug_lvl > 1:
							print("===:no lines found for xbib %i (label %s)"
									 % (j,xlabel), file=sys.stderr)
						
						# incomplétude constatée du résultat à l'étape link_lines
						checklist[1] = False
						continue
					
					else:
						# report des balises sur chaîne de caractères réelle
						(my_bibl_str, success) = match_fields(
													group_of_real_lines,
													subtrees = [this_xbib],
													label   = xlabel,
													debug_lvl   = debug_lvl,
													# bibfields
													model_type = the_model_type
												   )
						#~ if not success:
							#~ print("BIBFIELDS NO SUCCESS", file=sys.stderr)
						
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
						#     -------------                  vvvvvvvvvvv
						yield("<!--"+out_check_trigram+"-->"+my_bibl_str)
			
			# EXEMPLES DE SORTIE
			# -------------------
			# 111:<bibl> <author>Whittaker, J.</author>   (<date>1991</date>).   <title level="a">Graphical Models in Applied Multivariate Statistics</title>.   <publisher>Chichester: Wiley</publisher>. </bibl>

			# 111:<bibl> <author>Surajit Chaudhuri and Moshe Vardi</author>.  <title level="a">On the equivalence of recursive and nonrecursive data-log programs</title>.   In <title level="m">The Proceedings of the PODS-92</title>,   pages <biblScope type="pp">55-66</biblScope>,   <date>1992</date>. </bibl>
			
			# TODO: pour 'citations' ajouter aussi les non alignées != groups_by_xid comme pour l'autre
			
			# voilà fin mode 2
			
			# tail
			tail="""
		</listBibl>
	</text>
</tei>"""
			yield (tail)
		
		
		
		# ------------------------------------------------------------------
		#  mode 3: names: presque la même que en mode 2
		#                 mais garde 'forename', 'lastname' lors de XELT2TOK
		#                 et supprime tout le reste !
		#   --------------------------------------------------------
		elif the_model_type == "authornames":
			# le header est un peu différent que pour les bibfields
			header="""<?xml version="1.0" encoding="UTF-8"?>
<tei type="grobid.train.names">
	<teiHeader>
		<fileDesc xml:id="%s">
			<sourceDesc>
				<biblStruct>
					<analytic>""" % DOCID
			yield (header)
			
			print ("∤" * 80, file=sys.stderr)
			
			# ∤∤∤∤∤∤∤∤∤∤ ensuite comme pour les bibfields ∤∤∤∤∤∤∤∤∤∤
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
			if debug_lvl >= 1:
				# linked results
				print("="*70, file=sys.stderr)
				for j in range(nxb):
					xml_info = rag_xtools.glance_xbib(xbibs[j], longer = True)
					if rawlinegroups_by_xid[j] is None:
						print(xml_info + "\n<==> NONE", file=sys.stderr)
					else:
						print(xml_info + "\n<==>\n" + rawlinegroups_by_xid[j], file=sys.stderr)
					print("="*70, file=sys.stderr)
			
			
			#  ------------------------------           ===================
			#  Projection champs sur le texte et boucle OUTPUT mode auteurs
			#  ------------------------------           ===================
			print("---\nLINK PBIB TOKENS <=> XBIB FIELDS\n", file=sys.stderr)
			
			# report de chaque champ
			bibl_found_array = []
			
			max_j = len(rawlinegroups_by_xid) - 1
			
			# comme au précédent mode...
			# itération simultanée sur les xbibs et les rawlines qui leur ont été associées
			#             (index j => this_xbib)
			for j, group_of_real_lines in enumerate(rawlinegroups_by_xid):
					
					# la dernière est parfois vide
					if (group_of_real_lines is None) and (j == max_j):
						continue
					
					try:
						this_xbib = xbibs[j]
					except IndexError as ie:
						print("Auteurs: bib %i absente dans xbibs pour '%s'" % 
									   ( j, 
										 group_of_real_lines ),
						file=sys.stderr)
						# on donne un biblStruct vide
						this_xbib = etree.Element('biblStruct', type="__xbib_non_listée__")
					
					xlabel = readed_label[j]
					
					toks = []
					
					if group_of_real_lines is None:
						if debug_lvl > 1:
							print("===:no lines found for xbib %i (label %s)"
									 % (j,xlabel), file=sys.stderr)
						
						# incomplétude constatée du résultat à l'étape link_lines
						checklist[1] = False
						continue
					
					else:
						au_groups = this_xbib.findall("tei:analytic/tei:author", namespaces={'tei': "http://www.tei-c.org/ns/1.0"})
						
						# debug
						#~ print("groupes_bib_%i:"%j,au_groups, file=sys.stderr)
						
						my_work_line = group_of_real_lines
						
						# --------------------------------------------------
						# report des balises sur chaîne de caractères réelle
						# --------------------------------------------------
						(authors_str, success) = match_fields(
													my_work_line,
													subtrees = au_groups,
													debug_lvl = debug_lvl,
													# authornames
													model_type = the_model_type,
												   )
						
						# update 3è slot checklist pour filtrage erreurs
						checklist[2] = success
						

						
						# pour la sortie : filtre ex: 111 => tout bon
						# traduction de la checkliste en "101", "111", etc
						out_check_trigram = "".join([str(int(boul))
													  for boul in checklist])
						
						# séparateur saut de ligne dans le cas 'auteurs'
						authors_str = re.sub("¤","<lb/>",authors_str)
						
						
						#  => sortie finale au_str format 'auteurs'
						#     -------------                              vvvvvvvvvvv
						yield("<!--bib_%i:au:"%j+out_check_trigram+"-->"+authors_str)
			
			# EXEMPLES DE SORTIE
			# -------------------
			# <!--bib_14:au:111--><lastname>Barraquer-Ferre</lastname>, <forename>L.</forename>
			# <!--bib_15:au:111--><lastname>Millichap</lastname>, <forename>J. G.</forename>, <lastname>Lombroso</lastname>, <forename>C. T.</forename>, and <lastname>Len-nox</lastname>, <forename>W. G.</forename>
			# (...)
			
			
			# £TODO: problème si match sur toute la group_of_real_lines
			#        => la workline devrait être un segment auteur|éditeur
			#           déjà issu de bibfields et non pas toute la bib de biblines
			# exemple du pb
			# --------------
			# <lastname>Amenta</lastname> <forename>PS</forename>,
			# <lastname>Gil</lastname> <forename>J</forename>,
			# and <lastname>Martinez-Hernandez</lastname>
			# <forename>A</forename> (1988) Connective tissue of rat 
			# lung II: Ultrastructural localization of collagen types III,
			# IV, and VI. <forename>J</forename>
			#             ^^^^^^^^^^^^^^^^^^^^^^
			
			# voilà fin mode 3
			
			# tail
			tail="""
					</analytic>
				</biblStruct>
			</sourceDesc>
		</fileDesc>
	</teiHeader>
</TEI>"""
			yield (tail)
		
		else:
			print("Le modèle que vous avez choisi '%s' est inconnu. Les modèles connus sont 'bibzone', 'biblines', 'bibfields' et 'authornames'" % the_model_type)
			return None


# --------------------------------------------------------












###############################################################
########################### M A I N ###########################
###############################################################

if __name__ == "__main__":
	# diagnostic
	# ===========
	# les bools de la checkliste de diagno
	# restent vrai ssi les étapes respective 
	# BIBZONE, BIBLINES et BIBFIELDS se passent bien
	hope = [True, True, True]

	# options et arguments
	# ====================
	parser = prepare_arg_parser()
	args = parser.parse_args(sys.argv[1:])


	# défault pdfin
	if args.pdfin == None and args.txtin == None :
		temp = re.sub(r'tei\.xml', r'pdf', args.xmlin)
		temp = re.sub(r'teixml', r'pdf', temp)
		temp = re.sub(r'tei', r'pdf', temp)
		args.pdfin = re.sub(r'xml', r'pdf', temp)
		print("PDFIN?: essai de %s" % args.pdfin, file=sys.stderr)

	# vérification cohérence pour les 3 modèles préférant 
	# des flux texte spéciaux
	if (args.model_type in ["biblines", "bibfields", "authornames"] 
		and not args.txtin):
		print("""L'arg -m '%s' requiert un fichier texte -t ad hoc. 
		(utiliser bako.py make_trainer ou bien directement
		les cibles maven createTraining* de grobid-trainer)"""
			  % args.model_type,
			  file=sys.stderr)
		sys.exit(1)

	# lancement +++++++++++++++++++++++++++++++++++++++++++
	# la sortie du run est un générateur (print => yield)
	gen = run(
				the_model_type = args.model_type,
				the_pdfin      = args.pdfin,
				the_txtin      = args.txtin,
				the_xmlin      = args.xmlin,
				do_mask        = args.mask,
				checklist = hope,
				debug_lvl     = args.debug,
			)
	
	# on imprime les lignes du générateur
	for line in gen:
		if line is None:
			print("LINE A NONE===========================================")
			print("LINE A NONE===========================================", file=sys.stderr)
		print(line)


