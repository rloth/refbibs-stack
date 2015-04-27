#! /usr/bin/python3

import re
import sys
from lxml import etree
from xml.sax.saxutils import escape


NSMAP = {'tei': "http://www.tei-c.org/ns/1.0"}


# --------------------------------------------------------
# -A- helpers

# --------------------------------------------------------

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


def strip_inner_tags(match):
	"""
	Takes a re 'match object' on xml content and removes its inner XML tags à la xsl:value-of()
	Ex: "<au>Merry</au> and <au>Pippin</au>"
	    => <au>Merry and Pippin</au>
	"""
	capture = match.group(0)
	top_mid_bot=re.match(r"^(<[^>]+>)(.*)(<[^>]+>)$",capture)
	if (top_mid_bot is None):
		print("CLEAN_TAG_ERR: capture doesn't start and end with xmltags"
		      , file=sys.stderr)
		return(capture)
	else:
		tmb3 = top_mid_bot.groups()
		ltag  = tmb3[0]
		inner = tmb3[1]
		rtag  = tmb3[2]
		
		# strip
		inner = re.sub(r"<[^>]*>","",inner)
		
		# ok
		return (ltag+inner+rtag)


def str_escape(s):
	"""
	Takes string of raw content and escapes xml-unsafe chars "<" ">" "&"
	
	Ex: "Pilote <mâtin quel journal!>"
	    => "Pilote &lt;mâtin quel journal!&gt;"
	"""
	#~ s = re.sub("&", "&amp;", s)
	#~ s = re.sub("<", "&lt;", s)
	#~ s = re.sub(">", "&gt;", s)
	
	return escape(s)


# --------------------------------------------------------
# -B- fonctions xpath et nettoyage value-of

def simple_path(xelt, relative_to = ""):
	"""Construct a path of local-names from tag to root
	   or up to a local-name() provided in arg "rel_to"
	"""
	# starting point
	the_path = localname_of_tag(xelt.tag)
	if the_path == relative_to:
		return "."
	else:
		# ancestor loop
		for pp in xelt.iterancestors():
			pp_locname = localname_of_tag(pp.tag)
			if pp_locname != relative_to:
				# prepend elts on the way
				the_path = pp_locname + "/" + the_path
			else:
				# reached chosen top elt
				break
	# voilà
	return the_path

def localname_of_tag(etxmltag):
	"""
	Strip etree tag from namespace à la xsl:local-name()
	"""
	return re.sub(r"{[^}]+}","",etxmltag)






