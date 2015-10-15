#! /usr/bin/R
# --------------------------------------------------------
# PARAMETRES ET SWITCHES
# --------------------------------------------------------

# essentiels
# t = merge (tbib,pardoc, by.x="tdoc_id", by.y="eval_ID")
# RPbarplot(rplin(table(t$doctype,t$match)))

args=(commandArgs(TRUE))

# on montre les args
args

do.presentation = (length(args) > 2) && args[2] == "baseline_mode"

# TABLEAU DETAIL
# ---------------
# ex: workshop/evaluations/eval500-BASELINE-GB_0.3/tableau_detail_eval.tab"
inputfile = args[1]
#~ inputfile = "/home/loth/refbib/adapt-dir/evaluations/eval517-BASELINE-GB_0.3.4_avec_vanillas/tableau_detail_eval.tab"

# INFOS PAR DOCUMENTS
# --------------------
pardocfile = args[2]
#~ pardocfile = "/home/loth/refbib/adapt-dir/corpora/eval517/meta/infos.tab"

# /!\ avec_sb_seuls => manque 163 lignesdocs


# -----------------
# COLNAMES PARDOC
# -----------------
# 4 colonnes attendues (pour croisements)
# dans la table par documents:
#  - corpus
#  - pub_period
#  - doctype_1 ("ARTICLES", "NEWS", "COR", etc)
#  - cat_sci

# + 1 essentielle : bname (pour ID et pivot)

# + £TODO : lang, issn


 

# todo recodage an+mo mo ~~~> ? bibpubtype
# comme ancien do.analytic ?
do.pubtype = FALSE

options(OutDec = ",")     # séparateur de décimales

# --------------------------------------------------------

# Remarques 
# ==========

	# NOTATIONS
	# t sera la table issue de eval_xml_refbibs
	# gt correspond à t sans le bruit
	# tt    ' '     à t sans le silence
	# mt    ' '     à l'intersection (refbibs alignées)
	# pardoc est la table des infos au niveau document

	# USAGE
	# t$match contient l'éval de ch. refbib (bien trouvé="aligné", "bruit", "silence")
	# Et l'évaluation pour chaque champ est dans t$nomchamp (par ex t$date)

	# Tout croisement avec t$match peut être ensuite représenté en rappel ou précision
	# > rplin(table(t$nbgbibs_5bins, t$match))

	# et affiché
	# > RPbarplot(rplin(table(t$nbgbibs_5bins, t$match)))

	# Le script génère ainsi les éléments d'un rapport d'une 15aine de pages
	# dans le dossier courant dans 'rapport.txt' (en append) et les figures
	# svg correspondantes

	# TODO
	# réfléchir à l'usage d'une mesure de gain (rappel1 / rappel2) cf. l.440



# fonctions auxiliaires
# =====================
source("~/refbib/bin/lib_fonctions_rapport_eval.r")

# préparation des tables de données
# ==================================

# table sortie de eval_xml_refbibs.pl
# tbib = read.table("1943_008.tab", sep="\t", header=TRUE)
tbib = read.table(inputfile, sep="\t", header=TRUE, na.strings="___")

# fusion avec les infos par document
# ----------------------------------
# /!\ peut contenir des titres avec caras bizarres
# ==> on n'accepte aucun type de quote ni de comments
#     la tabulation est la seule règle pour distinguer les cols
pardoc = read.table(pardocfile, sep="\t", header=TRUE, 
         quote="", comment.char="")


#/!\ bname = doit correspondre à la var 08 "fileids"
#                              chez corpusdirs.Corpus()
# ici ex:  "els-C71674F4C0CC54423F9773ACACA9F6B407345546"
#     ou:  "oup-B7E571D1A0F4D61355A7FF07D8C2DFDFB84FEAEE"
pardoc$bname = paste(pardoc$corpus,pardoc$istex_id, sep="-")


# recodage résultats X pardoc
# ---------------------------
Mdoc = as.matrix(table(tbib$tdoc_id, tbib$match))

# permet R/P par doc si on veut:
	# RPbarplot(rplin(Mdoc))

# liste des documents où aligné == 0
ls_docs_zeros_align = rownames(Mdoc[Mdoc[,1] == 0,])
# liste des documents qui sortent vides (ie aligné ET bruit == 0)
ls_docs_sort_vide = rownames(Mdoc[Mdoc[,1]+Mdoc[,2] == 0,])
# report dans la liste pardoc
pardoc$sorties = ifelse(pardoc$bname %in% ls_docs_sort_vide,"tous_vides",ifelse(pardoc$bname %in% ls_docs_zeros_align,"tous_bruits","l_alignables"))


# ======================================8<============
# immédiats
# ==========
# rule de matching X (avec_analytic vs monogr_seul)
# table(tbib$tei_analytic, tbib$match_rule)

#        heuri:ti+autres strict:au+date strict:j+vol+p strict:ti+date
#  an+mo               3             17            191            166
#  mo                  0             22              0              5

# documents selon le nombre de lignes d'évaluations
# plot(sort(table(tbib$tdoc_id)))
# ======================================8<============


# pour la suite on amincit les données:
# on n'est pas forcés de garder author et title,
# et on a déjà repris istex_id et pub_year dans bname et pubb_period
pardoc = subset(pardoc, select=-c(author_1, title,pub_year,istex_id))



#######################################################
# T A B L E   P R I N C I P A L E
# T A B L E   P R I N C I P A L E
#######################################################
t = merge (tbib,pardoc, by.x="tdoc_id", by.y="bname")
#######################################################

# filtrages
# ----------
t = t[t$pdfver != "data",]
t = t[t$pdfver != "empty",]

	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# cela permet d'agréger les données bruit/silence
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# exemple :
	 #>LIGNESXdoctype = table(t$doctype,t$match)
		#           aligné  bruit silence
		#  ANN_VAR     205    133     139
		#  ARTICLES 136190  48871   58467
		#  INDXMISC     80     62     196
		#  NEWS_COR   3787   2376    2657
		#  REVLIT     9240   2809    3747
		#  SHORT       716    152     278
		
#~ 		                   aligné bruit silence
#~   research-article     32    12       5
#~   review-article        0     0      41
#~   Serial article      114    57      91
#~   UNKOWN_GENRE        203    36     210


	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


########################################################################
# Recodages et par champs


# sous-tables utiles
# ------------------
# table des golds
gt=t[!is.na(t$gbib_id), ]   # (ce qui veut dire != "___")

# table des todo
tt=t[!is.na(t$tbib_id), ]   # (ce qui veut dire != "___")

# mt table des alignés au niveau refbib
mt = t[t$match == "aligné", ]


# valeur max_periode pour réordonner les périodes alpha => chrono
# (alphabetiquement les périodes lucene se rangent dans l'ordre sauf la première qui passe en dernier)
max_periode=length(table(t$pub_period))


# ===========================================================================
# stats d'ensemble sur les données de croisement qu'on a pour le corpus gold
# ===========================================================================
if (do.presentation) {
	write("Préalable: Présentation du corpus gold\n\n", "rapport.txt", append=T)

	# NIVEAU REFBIB
	# --------------
#~ 	if(do.pubtype) {
#~ 		# pubtype :
#~ 		# ----------
#~ 		gstats.pbt = varstats(varname="pubtype_reco", niveau="bib", bibtable=gt, doctable=pardoc)
#~ 		gstats.pbt = gstats.pbt[3:1,]  # renversement pour que "autres" soit à la fin
#~ 		# % colonnes
#~ 		gstats.pbt.pc = 100*pccol(gstats.pbt, tot=T)
#~ 		# lignes des totaux
#~ 		gstats.pbt = rbind(gstats.pbt,TOTAL=colSums(gstats.pbt))
#~ 
#~ 		rapport(gstats.pbt, header="Type de publication de ch. refbib dans le corpus gold")
#~ 		rapport(gstats.pbt.pc, header="% colonnes")
#~ 
#~ 		## Figure 1
#~ 		# celui-ci mérite une figure
#~ 		svg("rapport_1a_PC-refs-champs-names_X_pubtype.svg", width=12, height=8)
#~ 		PCbarplot(gstats.pbt.pc, col.names="Distribution par type de publication (aux 3 échelons de données du corpus gold)")
#~ 		dev.off()
#~ 	}

	## pas de relation avec le calibre
	# PCbarplot(100*t(pclin(table(t$nbgbibs_5bins, t$pubtype_reco))))

	## relation légère avec la version pdf notamment 1.3 != des autres
	# PCbarplot(t(pclin(table(t$pdfver, t$pubtype_reco), tot=T)*100))


	# NIVEAU DOCUMENT
	# ---------------

	# corpus/lot :
	# -------------------
	gstats.lot = varstats(varname='corpus', niveau = "doc", bibtable=gt, doctable=pardoc)
	
	gstats.lot.pc = 100*pccol(gstats.lot, tot=T)
	gstats.lot = rbind(gstats.lot,TOTAL=colSums(gstats.lot))
	rapport(gstats.lot, header="0.a - Détail des volumes selon le lot (corpus src)")
	rapport(gstats.lot.pc, header="% colonnes")

	svg("rapport_0a_PC-corpus_par_lot.svg", width=12, height=8)
	PCbarplot(gstats.lot.pc, col.names="Distribution dans l'échantillon par lots", color=4)
	dev.off()



	# pdfver :
	# --------
	gstats.pdf = varstats(varname="pdfver", niveau="doc", bibtable=gt, doctable=pardoc)

	# Exemple
	#     nDocs nBibs nChamps nAuteurs
	# 1.2    25  1158    7600     4482
	# 1.3   872 41154  265710   132221
	# 1.4   759 34913  233381   100819
	# 1.5    78  2941   19803     9373
	# 1.6   147  7597   52435    25255
	# 1.7     4   356    2482      495

	# % colonnes
	gstats.pdf.pc = 100*pccol(gstats.pdf, tot=T)

	# lignes des totaux
	gstats.pdf = rbind(gstats.pdf,TOTAL=colSums(gstats.pdf))

	rapport(gstats.pdf, header="Versions PDF des documents du corpus")
	rapport(gstats.pdf.pc, header="% colonnes")


	# periode de publi :
	# -------------------
	gstats.periode = varstats(varname='pub_period', niveau = "doc", bibtable=gt, doctable=pardoc)
	
	# avec les pub_period la dernière est en fait la première, les autres dans l'ordre
	gstats.periode = gstats.periode[c(max_periode,1:(max_periode-1)),]
	gstats.periode.pc = 100*pccol(gstats.periode, tot=T)
	gstats.periode = rbind(gstats.periode,TOTAL=colSums(gstats.periode))
	rapport(gstats.periode, header="0.b -- Détail des volumes selon la période de publication")
	rapport(gstats.periode.pc, header="% colonnes")

	svg("rapport_0b_PC-corpus_par_periode_publication.svg", width=12, height=8)
	PCbarplot(gstats.periode.pc, col.names="Distribution dans l'échantillon par grande période", color=7)
	dev.off()

	# TODO
#~ 	tgstats.periode.pc = 100*pccol(t(gstats.periode), tot=T)


	# croisement Version PDF X periode 
	ostats.pdfXperiode = 100*pclin(table(pardoc$pub_period, pardoc$pdfver), tot=T)
	
	# idem que gstats : on range les lignes (ordre alpha) => (ordre chrono)
	ostats.pdfXperiode = ostats.pdfXperiode[c(max_periode,1:(max_periode-1)),]
	
	rapport(ostats.pdfXperiode, "0.c -- Distribution des versions PDF par periode de publication")

	svg("rapport_0c_PC-pdfver_X_periode.svg", width=12, height=8)
	PCbarplot(t(ostats.pdfXperiode), col.names="Distribution des versions PDF par periode", color=3)
	dev.off()



	# genre/doctype :
	# -------------------
	gstats.subtype = varstats(varname='doctype_1', niveau = "doc", bibtable=gt, doctable=pardoc)
	gstats.subtype.pc = 100*pccol(gstats.subtype, tot=T)
	gstats.subtype = rbind(gstats.subtype,TOTAL=colSums(gstats.subtype))
	rapport(gstats.subtype, header="0.d -- Détail des volumes selon le type de document")
	rapport(gstats.subtype.pc, header="% colonnes")

	svg("rapport_0d_PC-corpus_par_subtype.svg", width=12, height=10)
	PCbarplot(gstats.subtype.pc, col.names="Distribution dans l'échantillon par grand type de document", color=2)
	dev.off()




	# thème via ISSN: 
	# ---------------
	gstats.theme = varstats(varname='cat_sci', niveau = "doc", bibtable=gt, doctable=pardoc)
	gstats.theme.pc = 100*pccol(gstats.theme, tot=T)
	gstats.theme = rbind(gstats.theme,TOTAL=colSums(gstats.theme))
	rapport(gstats.theme, header="0.e -- Détail volumétrie, selon thème WOS si attribué")
	rapport(gstats.theme.pc, header="% colonnes")


}

# tableaux croisés sur alignement refbib par métadonnées dispo
# ============================================================
# syntaxe: table(lignes,colonnes)

write("1- Rappel et précision macro (croisés par variables doc)\n\n", "rapport.txt", append=T)


# LOT
# ------
# Tableau croisé
Mlot = table(t$corpus, t$match)

# ajout 2 colonnes rappel et précision
Mlot.rp = rplin(Mlot)

# sortie Mlot.rp >> rapport.txt
rapport(Mlot.rp, header="1.a -- Refbibs alignées, selon le lot")

# Figure (graphique à barres) pour les rappels et précisions
svg("rapport_1a_RP-par-ref_X_lot.svg", width=12, height=8)
RPbarplot(Mlot.rp, xlabel="lot (corpus src) du document")
dev.off()

## Figure 2bx  -- scatterplot rappel/précision
svg("rapport_1ax_RP-lot_scatterplot_R-P.svg", width=12, height=12)
# las = 2 pour labels verticaux
plot(Mlot.rp[,4],Mlot.rp[,5],xlab="rappel", ylab="précision")
text(Mlot.rp[,4],Mlot.rp[,5], labels=rownames(Mlot.rp))
dev.off()


# PDFVER
# ------
# Tableau croisé
Mpdf = table(t$pdfver, t$match)

# ajout 2 colonnes rappel et précision
Mpdf.rp = rplin(Mpdf)

# sortie Mpdf.rp >> rapport.txt
rapport(Mpdf.rp, header="1.b -- Refbibs alignées, selon version pdf")

## Figure 1b
# Figure (graphique à barres) pour les rappels et précisions
svg("rapport_1b_RP-par-ref_X_pdfver.svg", width=12, height=8)
RPbarplot(Mpdf.rp, xlabel="version pdf du document")
dev.off()

## Figure 1bx  -- scatterplot rappel/précision
svg("rapport_1bx_RP-pdfver_scatterplot_R-P.svg", width=12, height=12)
# las = 2 pour labels verticaux
plot(Mpdf.rp[,4],Mpdf.rp[,5],xlab="rappel", ylab="précision")
text(Mpdf.rp[,4],Mpdf.rp[,5], labels=rownames(Mpdf.rp))
dev.off()


# PERIODE
# ------
# Rappels et précisions par periode
Mperiode = table(t$pub_period, t$match)

# ordre alpha => ordre chrono
Mperiode = Mperiode[c(max_periode,1:(max_periode-1)),]

Mperiode.rp = rplin(Mperiode)
rapport(Mperiode.rp, header="1.c -- Refbibs alignées, par période de publication")

## Figure 1c
svg("rapport_1c_RP-par-ref_X_periode.svg", width=14, height=9)
# las = 2 pour labels verticaux
RPbarplot(Mperiode.rp, xlabel="période de publication")
dev.off()


# genre/doctype :
# ---------------
# Rappels et précisions par subtype
Msubtype = table(t$doctype_1, t$match)
Msubtype.rp = rplin(Msubtype)
rapport(Msubtype.rp, header="1.d -- Refbibs alignées, par genre (type de doc)")

## Figure 1d
svg("rapport_1d_RP-par-ref_X_genre.svg", width=14, height=9)
# las = 2 pour labels verticaux
RPbarplot(Msubtype.rp, xlabel="type de document")
dev.off()



# THEME
# ------
# Rappels et précisions par theme
Mtheme = table(t$cat_sci, t$match)
Mtheme.rp = rplin(Mtheme)
rapport(Mtheme.rp, header="1.e -- Refbibs alignées, par thème WOS de l'ISSN du doc")

## Figure 1e  -- scatterplot rappel/précision
svg("rapport_1e_RP-theme_scatterplot_R-P.svg", width=12, height=12)
# las = 2 pour labels verticaux
plot(Mtheme.rp[,4],Mtheme.rp[,5],xlab="rappel", ylab="précision")
text(Mtheme.rp[,4],Mtheme.rp[,5], labels=rownames(Mtheme.rp))
dev.off()


# Autre format: le type à l'arrivée
# tei_analytic (pour todo => aligné et bruit => Précision seule)
Mteitype.r = plin(table(t$tei_analytic,t$match))
rapport(Mteitype.r, header="1.f -- Précision à l'arrivée, selon type de publication formée par grobid en sortie de balisage")

## Figure 1f
svg("rapport_1f_P-par-ref_X_teitype.svg", width=6, height=8)
Qbarplot(Mteitype.r, xlabel="type de ref (monogr. seule ou analytique+monogr.)\n[sans comparer avec le gold]")
dev.off()



# pour info série "1z": récap de sorties (résultat global pour ch. document)
# -----------------------------------------------------------------------------

write("Les résultats par doc sont ici un résumé du taux d'alignement obtenu pour ce doc. On distingue :\n
  - les docs qui sortent avec quelques (au moins une) lignes alignables\n
  - les docs qui sortent avec uniquement du bruit\n
  - les docs qui sortent sans aucune refbib\n
Les 2 derniers cas sont souvent causés par un mauvais repérage de la section 'Références' dans le texte.\n\n", "rapport.txt", append=T)


# Récapitulatifs (par lot) de résultat global (tous bruit, tous vide, qqs alignés au moins)
rawdocs_sortiesXlot = table(pardoc$corpus, pardoc$sorties, dnn=c('', 'récap résultat'))
docs_sortiesXlot.pc = 100*pclin(rawdocs_sortiesXlot, tot=T)
docs_sortiesXlot = table2df(rawdocs_sortiesXlot, marginsums=c(1,2))
rapport(docs_sortiesXlot, header="1.za -- Récapitulatif d'alignements par doc, selon lot (corpus src)")
rapport(docs_sortiesXlot.pc, header="% lignes")

svg("rapport_1za_PC-sortiesdoc_X_lot.svg", width=14, height=9)
PCbarplot(t(docs_sortiesXlot.pc), color=6, col.names="Récapitulatif d'alignements par doc, selon lot (corpus src)")
dev.off()

# par version pdf
rawdocs_sortiesXpdf = table(pardoc$pdfver, pardoc$sorties,dnn=c("","récap résultat"))
docs_sortiesXpdf.pc = 100*pclin(rawdocs_sortiesXpdf, tot=T)
docs_sortiesXpdf = table2df(rawdocs_sortiesXpdf, marginsums=c(1,2))
rapport(docs_sortiesXpdf, header="1.zb -- Récapitulatif d'alignements par doc, selon version pdf")
rapport(docs_sortiesXpdf.pc, header="% lignes")

## Figure 2az  -- récap sorties selon pdfver
svg("rapport_1zb_PC-sortiesdoc_X_pdfver.svg", width=12, height=6)
PCbarplot(t(docs_sortiesXpdf.pc), color=6, col.names="Récapitulatif d'alignements par doc, selon version pdf")
dev.off()


# Récapitulatifs (par periode) de résultat global (tous bruit, tous vide, qqs alignés au moins)
rawdocs_sortiesXperiode = table(pardoc$pub_period, pardoc$sorties, dnn=c('', 'récap résultat'))

rawdocs_sortiesXperiode = rawdocs_sortiesXperiode[c(max_periode,1:(max_periode-1)),]

docs_sortiesXperiode.pc = 100*pclin(rawdocs_sortiesXperiode, tot=T)
docs_sortiesXperiode = table2df(rawdocs_sortiesXperiode, marginsums=c(1,2))
rapport(docs_sortiesXperiode, header="1.zc -- Récapitulatif d'alignements par doc, selon période de publication")
rapport(docs_sortiesXperiode.pc, header="% lignes")

svg("rapport_1zc_PC-sortiesdoc_X_periode.svg", width=14, height=9)
PCbarplot(t(docs_sortiesXperiode.pc), color=6, col.names="Récapitulatif d'alignements par doc, selon période de publication")
dev.off()

###########################################################################################
###########################################################################################


# tables sur alignement par champs
# ================================

write("2-TABLES PAR CHAMPS\n\n", "rapport.txt", append=T)

write("NB: l'obtention des valeurs par champs étant couplée à l'obtention des résultats par ligne de refbib, les valeurs obtenues \"héritent\" en grande partie des taux au niveau macro\n\n", "rapport.txt", append=T)

write("2A-Rappel et précision pour chaque champ\n\n", "rapport.txt", append=T)

# on va compacter la grande table par bib comparée en une table agrégée "totaux résultat obtenu pour chaque champs"

# la série des colonnes par champs dans t
bibchamps=data.frame(namez=sub("^F","",grep ("^F", colnames(tbib), value=T)), colz=grep("^F", colnames(t)))

#~   namez colz
#~ 1   tit   10
#~ 2  date   11
#~ 3     j   12
#~ 4   vol   13
#~ 5   iss   14
#~ 6   fpg   15
#~ 7   lpg   16
#~ 8 psher   17

nchamps = nrow(bibchamps)


# tous les résultats possibles
evaloutcomes = table(as.vector(as.matrix(t[,bibchamps$colz])))
#~                    NON_bruit             NON_bruit_captif 
#~                          184                          335 
#~                     NON_diff                  NON_silence 
#~                          227                           67 
#~           NON_silence_captif                          OUI 
#~                         1513                         1425 
#~          OUI_avec:allongé.OK           OUI_avec:norpun.OK 
#~                            2                           27 
#~ OUI_avec:norpun.raccourci.OK           OUI_avec:OCeeRs.OK 
#~                            6                            8 
#~        OUI_avec:raccourci.OK           OUI_avec:rmhyph.OK 
#~                           14                            5 

moutcomes = length(evaloutcomes)
print(moutcomes)
# table pour notre collecte 'résumé par champ'
Mx = matrix(rep(0, nchamps*moutcomes), ncol=moutcomes)
Dx = data.frame(Mx)


########
# Approche de remplissage naïve ligne par ligne => ne va pas aller !
# en effet table() n'aura pas toujours le même nombre de valeurs
# (certains résultats n'ont jamais eu lieu pour certains champs)
# for (i in 1:nrow(bibchamps)) { Dx[i,] = table(t[,bibchamps$cols[i]]) }
########


# on utilisera donc ces names comme liste "CANON" 
# de tous les j possibles (et tjs dans le même ordre)
colnames(Dx) = names(evaloutcomes)


# pour la boucle par ligne c'est plus normal
rownames(Dx) = bibchamps$names


# pour travailler aux sommes pour chaque champs on utilise la sortie de table() mais transposée
# astuce : permettra d'accéder aux nbvaleurs par les noms des valeurs dans TRUC
#        ==>  as.data.frame(t(as.matrix(table(TRUC)))) <==


for (i in 1:nrow(bibchamps)) {
	champ.col = bibchamps$colz[i]
	champ.nom = bibchamps$namez[i]
	print(paste('champ', champ.nom))
	
	# table de travail
	tt = as.data.frame(t(as.matrix(table(t[,champ.col]))))
	
	for (j in 1:length(evaloutcomes)) {
		jname = names(evaloutcomes)[j]
		ini.nbvalj = tt[,which(names(tt)==jname)]
		if (length(ini.nbvalj)) {
			# remplissage Dx
			Dx[i,j] = ini.nbvalj
		}
		# et sinon Dx[i,j] restera à 0
	}
}


# Avec codes résultats bruts
Mchqchamp.detail = Dx
Mchqchamp.detail[is.na(Mchqchamp.detail)] = 0
Mchqchamp.detail = data.frame(Mchqchamp.detail, TOTAL_def=rowSums(Mchqchamp.detail))
rownames(Mchqchamp.detail) = sub("^F","",grep ("^F", colnames(tbib), value=T))

rapport(Mchqchamp.detail, header="Résultats bruts par champ")








# Version recodée ET en ajoutant une ligne pour les authornames
# 


# on opère le recodage à petite échelle sur la table déjà agrégée
# ci-dessus mais si on veut + tard des sous-groupes détaillés 
# (par ex: le rappel du champ titre *parmi le lot elsevier*),
# alors il faudra lancer le recoSB toutes les entrées pour tous les 
# champs selon la table recoSB

Mchqchamp=rbind.fill(apply(F.reco.sil_brt,2, FUN=function (x) {as.data.frame(t(as.matrix(table(x))))}))
Mchqchamp[is.na(Mchqchamp)] = 0
rownames(Mchqchamp) = sub("^F","",grep ("^F", colnames(tbib), value=T))

# ajout des noms avec calcul indépendant -----------

# liste des colonnes 'agrégats names'
# (colonnes résumant les propriétés des alignements par auteurs)
# ie les indices des 3 colonnes: 
#   - gnames, tnames, oknames, 
nmcols2 = c(which(colnames(t) == "gnames"),which(colnames(t) == "tnames"),which(colnames(t) == "oknames"))

# les résultats bruts pour le champ auteur sont la somme des colonnes agrégats names
# (une seule ligne de totaux sur la grande table t)
Mauteurschamp = t(data.frame(champ_auteurs=colSums(as.matrix(t[,nmcols2]),na.rm=T)))

rapport(Mauteurschamp, header="Résultats bruts champ Auteurs")

# --------------------------------------------------
# mêmes sommes infos auteurs reprises séparément pour recodage
N.ali = sum(t$oknames)
N.bruit = sum(t$tnames, na.rm=T) - N.ali
N.silence = sum(t$gnames, na.rm=T) - N.ali

# ajout de ces infos auteurs à celles des autres champs
# (todo: ordre c(N.ali...) incertain pour format d'entrée de rplin.F)
Mchqchamp=rbind(Mchqchamp, "authors"=c(N.ali,N.bruit,0,0,N.silence))

write("Les codes de résultats vus à la table précédente sont dorénavant recodés : les éléments alignés (ie match strict, chaînes de caractères identiques) permettent de calculer un 'rappel strict' (noté Rs) et une 'précision stricte' (notée Ps).\nDe leur côté, l'ensemble des matchs élargis (en enlevant les tirets, les ligatures, en normalisant les espaces, etc) sont groupés en une colonne 'maisOK' qui permet de calculer un rappel élargi (noté R) et une précision élargie (notée P).\nOn appellera 'gain de rappel' la différence R - Rs, et 'gain de précision' la différence P - Ps\n\n", "rapport.txt", append=T)


# ----------------------------------------------------------------------------------------------
# TABLE CENTRALE
# ---------------

Mchqchamp.rp = rplin.F(Mchqchamp)
rapport(Mchqchamp.rp, header="Recodage des codes résultats pour obtenir rappel et précision")
## Figure 4a
svg("rapport_4a_RP-par-champ.svg", width=12, height=8)
RPbarplot.gain(Mchqchamp.rp, xlabel="élément XML (champ) concerné")
dev.off()

















###########################################################################################
###########################################################################################





























# recodage
# ---------

# recodage résultats par champs => colonnes par résultats, tous champs confondus
# (LONG A EFFECTUER: l'intégrer ce reco et la table partyperesultat dès le script
# eval_xml_refbib.pl ? TODO)
F.reco.sil_brt=sapply(t[,grep("^F", colnames(t))], function (col) {
	col=sub("^OUI$", "F.aligne", col);
	col=sub("^OUI_si_nettoie$", "F.aligne", col);
	col=sub("^NON_silence.*$","F.silence",col);
	col=sub("^NON_\\+court.*$","F.silence",col) ;
	col=sub("^NON_bruit.*$","F.bruit",col);
	col=sub("^NON_\\+long.*$","F.bruit",col) ;
	col=sub("^NON_diff$","F.les2",col) ;
# 	col=sub("^OUI_avec.*$","F.aligne",col) ;
	col=sub("^OUI_avec.*$","F.maisOK",col) ;
	})

colnames(F.reco.sil_brt) = paste("RecoSB",colnames(F.reco.sil_brt),sep="")
meslevels = as.data.frame(table(F.reco.sil_brt))[,1]
# Les lignes de résultats sont champs par champ et consistent en des codes résultats variés,
# or à présent on veut une colonne pour chaque code résultat tous champs confondus.
# Donc on procède de la façon suivante:
# Pour chaque code résultat 'k' possible (listé dans meslevels), 
#     ~ pour chaque ligne de résultats 'r', 
#         ~ on compte l'effectif de ce code résultat et on en crée une colonne
partyperesultat=data.frame(sapply(1:length(meslevels), function(k) {sapply(1:nrow(F.reco.sil_brt),function(r) {length(grep(meslevels[k], F.reco.sil_brt[r,]))})}))
colnames(partyperesultat) = paste("tsChamps",meslevels,sep=".")
	# [1] "tsChamps.F.aligne"  "tsChamps.F.bruit"   "tsChamps.F.les2"
	# [4] "tsChamps.F.silence" 

# réintegration des recodages
# ----------------------------
t = data.frame(t,F.reco.sil_brt)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# cela permettra d'agréger les données pour un champ donné
	# (cf. parties 4A-B)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# exemple :
	 #>FtitXpdfver = table(t$pdfver,t$RecoSBFtit)
		#       F.aligne F.bruit F.les2 F.silence
		#   1.2      280     242     74       729
		#   1.3    18812    4505   3581     14578
		#   1.4    12838    8945   1626     19133
		#   1.5     1433     350    341      1042
		#   1.6     4304     876    858      2193
		#   1.7      245      25     29        78
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


t = data.frame(t,partyperesultat)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# cela permettra d'agréger les données partyperesultat selon n'importe quel champ de t
	# (cf. partie 4C)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# par exemple pour agréger par pubtype:
	 #>tsChampsXpdfver = aggregate(as.matrix(t[,grep("tsChamps",colnames(t))]) ~ t$pdfver, t,sum)
	 #>rownames(tsChampsXpdfver) = tsChampsXpdfver[,1]
	 #>tsChampsXpdfver = tsChampsXpdfver[,-1]
		#       tsChamps.F.aligne   tsChamps.F.bruit   tsChamps.F.les2   tsChamps.F.silence
		# 1.2                2136                858               199                 4011
		# 1.3              126004              17746              7771                88732
		# 1.4               82595              18729              3630               111078
		# 1.5               10453               1313               832                 5352
		# 1.6               29866               2172              1528                13141
		# 1.7                1628                 65                56                  435

	# autre exemple pour agréger par doc_id :
	 #>tsChampsXdoc = aggregate(as.matrix(t[,grep("tsChamps",colnames(t))]) ~ t$tdoc_id, test,sum)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~





























###########################################################################################






# -----------------------------------------------------------------------------------------------
# TABLE détaillées
# ------------------

# 4.b-c-d-e: détail par lot/corpus pour DATE, TITRE, JOURNAL, VOLUME
# --------------------------------------------------------
write("Par lot:\n----------------------------\n", "rapport.txt", append=T)
# champ date
MdateXlot.rp = rplin.F(table.rm0(t$corpus,t$RecoSBFdate))
rapport(MdateXlot.rp, header="Champ DATE, selon familles typo")
## Figure 4b
svg("rapport_4b_RP_dateXlot.svg", width=12, height=5)
RPbarplot.gain(MdateXlot.rp, color=1, title="Rappel et précision du champ DATE", xlabel="lots (corpus source)")
dev.off()

# champ titre
MtitXlot.rp = rplin.F(table.rm0(t$corpus,t$RecoSBFtit))
rapport(MtitXlot.rp, header="Champ TITRE, selon corpus")
## Figure 4c
svg("rapport_4c_RP_titreXlot.svg", width=12, height=5)
RPbarplot.gain(MtitXlot.rp, color=1, title="Idem champ TITRE", xlabel="lots (corpus source)")
dev.off()

# champ journal
MjXlot.rp = rplin.F(table.rm0(t$corpus,t$RecoSBFj))
rapport(MjXlot.rp, header="Champ JOURNAL, selon corpus")
## Figure 4d
svg("rapport_4d_RP_journalXlot.svg", width=12, height=5)
RPbarplot.gain(MjXlot.rp, color=1, title="Idem champ JOURNAL", xlabel="lots (corpus source)")
dev.off()

# champ volume
MvolXlot.rp = rplin.F(table.rm0(t$corpus,t$RecoSBFvol))
rapport(MvolXlot.rp, header="Champ VOLUME, selon corpus")
## Figure 4e
svg("rapport_4e_RP_volumeXlot.svg", width=12, height=5)
RPbarplot.gain(MvolXlot.rp, color=1, title="Idem champ VOLUME", xlabel="lots (corpus source)")
dev.off()



# 4.f-g-h-i: détail par periode pour DATE, TITRE, JOURNAL, VOLUME
# ----------------------------------------------------------------
write("Par periode:\n----------------------------\n", "rapport.txt", append=T)

max_periode=length(table(t$pub_period))

# champ date
MdateXperiode.rp = rplin.F(table.rm0(t$pub_period,t$RecoSBFdate))

# ordre alpha => ordre chrono
MdateXperiode.rp = MdateXperiode.rp[c(max_periode,1:(max_periode-1)),]

rapport(MdateXperiode.rp, header="Champ DATE, selon période de publication")
## Figure 4b
svg("rapport_4f_RP_dateXperiode.svg", width=12, height=5)
RPbarplot.gain(MdateXperiode.rp, color=1, title="Rappel et précision du champ DATE", xlabel="période de publi.")
dev.off()

# champ titre
MtitXperiode.rp = rplin.F(table.rm0(t$pub_period,t$RecoSBFtit))
# ordre alpha => ordre chrono
MtitXperiode.rp = MtitXperiode.rp[c(max_periode,1:(max_periode-1)),]
rapport(MtitXperiode.rp, header="Champ TITRE, selon période de publication")
## Figure 4c
svg("rapport_4g_RP_titreXperiode.svg", width=12, height=5)
RPbarplot.gain(MtitXperiode.rp, color=1, title="Idem champ TITRE", xlabel="période de publi.")
dev.off()

# champ journal
MjXperiode.rp = rplin.F(table.rm0(t$pub_period,t$RecoSBFj))
# ordre alpha => ordre chrono
MjXperiode.rp = MjXperiode.rp[c(max_periode,1:(max_periode-1)),]
rapport(MjXperiode.rp, header="Champ JOURNAL, selon période de publication")
## Figure 4d
svg("rapport_4h_RP_journalXperiode.svg", width=12, height=5)
RPbarplot.gain(MjXperiode.rp, color=1, title="Idem champ JOURNAL", xlabel="période de publi.")
dev.off()

# champ volume
MvolXperiode.rp = rplin.F(table.rm0(t$pub_period,t$RecoSBFvol))
# ordre alpha => ordre chrono
MvolXperiode.rp = MvolXperiode.rp[c(max_periode,1:(max_periode-1)),]
rapport(MvolXperiode.rp, header="Champ VOLUME, selon période de publication")
## Figure 4e
svg("rapport_4i_RP_volumeXperiode.svg", width=12, height=5)
RPbarplot.gain(MvolXperiode.rp, color=1, title="Idem champ VOLUME", xlabel="période de publi.")
dev.off()


# Autres
# ------
# write("Autres:\n-------\n", "rapport.txt", append=T)
# # todo
# PCbarplot(t(100*pclin(table (mt$pdfver,mt$RecoSBFtit))))
# 
# 


#~ write("Pour info relation périodes <=> typobib\n", "rapport.txt", append=T)
#~ 
#~ truc.pc = pclin(t(table.rm0(t$periode,t$hclu12_nom)))
#~ truc.pc = truc.pc[c(4:12,1:3),]
#~ rapport(truc.pc, header="Période de publication, selon classe typobib")
#~ svg("rapport_5h_PC_periodeXtypobib.svg", width=12, height=8)
#~ PCbarplot(100*t(truc.pc), color=6, col.names="Récap période de publication selon style typographique du doc")
#~ dev.off()
