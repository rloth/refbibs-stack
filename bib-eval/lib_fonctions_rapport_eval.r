################# SOMMAIRE ##############################################
# cette librairie permet de rapidement comparer des données biblio

#======================
# Fonctions pratiques:
#======================

# varstats()      donne une vue d'ensemble
# ----------

	# > varstats (varname="pdfver", niveau="doc")
	# --------------------------------------------
	#   pdfver nDocs nBibs nChamps nAuteurs
	# 1    1.2    27  1158    7600     4482
	# 2    1.3   909 41154  265710   132221
	# 3    1.4   760 34913  233381   100819
	# 4    1.5    79  2941   19803     9373
	# 5    1.6   148  7597   52435    25255
	# 6    1.7     4   356    2482      495

	
# SI ==> on fait des tableaux croisés d'une variable avec t$match

# rplin()         pour ajouter 2 colonnes rappel et précision
# --------
# RPbarplot()     pour afficher un rplin()
# -----------

#             aligne bruit silence    R    P
# Q1 [1-26]     5696  2641    3052 0,65 0,68
# Q2 [27-38]    8661  3929    6556 0,57 0,69
# Q3 [39-55]   11490  4117    9095 0,56 0,74
# Q4 [56-546]  23463  5766   20106 0,54 0,80


# SI ==> on fait des tableaux croisés de deux variables quelconques
# pccol()         pour faire de % col
# -------
# et sa transposée pclin()  lignes
# PCbarplot pour afficher un pccol() en diagramme à barres empilées

# rapport()      pour >> du texte et une table tabulée 
# ----------             à un fichier rapport.txt

#########################################################################


rapport = function (matable, header="titre", outfile="rapport.txt") {
	write(header, outfile, append=T)
	write.table(matable, outfile, append = T, sep = "\t", col.names = NA, dec=",")
	write("\n", outfile, append=T)
}


# pclin(): table en % lignes
pclin = function (df, tot=F) {
	n = nrow(df)
	pc = df/rowSums(df)
	if(tot) {
		return (cbind(round(pc,3),TOTAL=rep(1,n)))
	}
	else {
		return (round(pc,3))
	}
}

# pccol(): table en % colonnes
pccol = function (df, tot=F) {
	m = ncol(df)
	pc = t(t(df)/colSums(df))
	if (tot) {
		return (rbind(round(pc,3),TOTAL=rep(1,m)))
	}
	else {
		return (round(pc,3))
	}
}

# rplin(): table en rappel/précision par lignes
# L'entrée attendue provient d'un appel table(qqch, t$match)
# ENTREE:
# -------
#     aligne bruit silence
# aaa    467   242     691
# bbb  24809  4954   16345
# ccc  15956 10002   18957

# SORTIE:
# -------
#     aligne bruit silence    R    P
# aaa    467   242     691 0,40 0,66
# bbb  24809  4954   16345 0,60 0,83
# ccc  15956 10002   18957 0,46 0,61
rplin = function(df) {
	s = which(colnames(df) == "silence")
	a = which(colnames(df) == "aligne")
	a =  ifelse(length(a),a,which(colnames(df) == "aligné"))
	b = which(colnames(df) == "bruit")
	
	R = round(df[,a] / (df[,a] + df[,s]), 2)  # rappel
	P = round(df[,a] / (df[,a] + df[,b]), 2)  # précision
	
	# on les colle direct à la fin de la table d'origine
	return (cbind(df, R, P))
}

rlin = function(df) {
	s = which(colnames(df) == "silence")
	a = which(colnames(df) == "aligne")
	a =  ifelse(length(a),a,which(colnames(df) == "aligné"))
	
	R = round(df[,a] / (df[,a] + df[,s]), 2)  # rappel
	
	# on les colle direct à la fin de la table d'origine
	return (cbind(aligne=df[,a],silence=df[,s], R))
}

plin = function(df) {
	a = which(colnames(df) == "aligne")
	a =  ifelse(length(a),a,which(colnames(df) == "aligné"))
	b = which(colnames(df) == "bruit")
	
	P = round(df[,a] / (df[,a] + df[,b]), 2)  # précision
	
	# on les colle direct à la fin de la table d'origine
	return (cbind(aligne=df[,a],bruit=df[,b], P))
}

# variante de rplin() pour les tableaux par champs qui ont des
# colonnes supplémentaires 'les2' (à la fois bruit et silence)
# et 'maisOK' (strictement bruit et silence mais ok moyennant
# petites transformations comme unligatures ou normalize_space)
rplin.F = function(df, rownames.col1 = F) {
	if (rownames.col1) {
		rownames(df) = df[,1]
		df = df[,-1]
	}
	s  = grep("F\\.silence$", colnames(df))
	a  = grep("F\\.aligne$", colnames(df))
	b  = grep("F\\.bruit$", colnames(df))
	bs = grep("F\\.les2$", colnames(df))
	
	# celui-ci n'est pas toujours existant ; 
	# sinon vaut => liste de longueur 0
	ma = grep("F\\.maisOK$", colnames(df))
		
	if (length(ma)) {
		# rappel strict (champs identiques)
		Rs = round(df[,a] / (df[,a] + df[,s] + df[,bs] + df[,ma]), 2)
		# précision stricte (champs identiques)
		Ps = round(df[,a] / (df[,a] + df[,b] + df[,bs] + df[,ma]), 2)
		
		# gain de rappel dû aux transformations 'maisOK'
		gR = round(df[,ma] / (df[,a] + df[,s] + df[,bs] + df[,ma]), 2)
		# gain de précision dû aux transformations 'maisOK'
		gP = round(df[,ma] / (df[,a] + df[,b] + df[,bs] + df[,ma]), 2)
	}
	else {
		Rs = round(df[,a] / (df[,a] + df[,s] + df[,bs]), 2)
		Ps = round(df[,a] / (df[,a] + df[,b] + df[,bs]), 2)
		gR = rep(0,nrow(df))
		gP = rep(0,nrow(df))
	}
		
		# Rappel total, incluant 'maisOK' comme si 'aligne'
		R = Rs + gR
		# Précision totale, incluant 'maisOK' comme si 'aligne'
		P = Ps + gP
	
	# on les colle direct à la fin de la table d'origine
	return (cbind(df, Rs, Ps, R, P))
}


# variante de rplin() pour les tableaux par noms qui ont déjà les colonnes faites
rplin.N = function(df, rownames.col1 = F, with.gain=F) {
	if (rownames.col1) {
		rownames(df) = df[,1]
		df = df[,-1]
	}
	g = which(colnames(df) == "gnames")
	a = which(colnames(df) == "oknames")
	t = which(colnames(df) == "tnames")
		
	# version détaillée (tables sur nmcols2)
	# (pour RPbarplot.gain)
	if (with.gain) {
		# on doit prendre ensemble les 4 cols de bruit rattrapé
		# (≈ F.maisOK pour les autres champs)
		c = which(colnames(df) == "capzkonames")
		w = which(colnames(df) == "weirdcharkonames")
		f = which(colnames(df) == "cutfieldkonames")
		p = which(colnames(df) == "particulekonames")
		N.maisOK = df[,c] + df[,w] + df[,f] + df[,p]

		# rappel strict (champs identiques)
		Rs = round(df[,a] / df[,g], 2)
		# précision stricte (champs identiques)
		Ps = round(df[,a] / df[,t], 2)
		
		# supplément rappel dû aux transformations
		gR = round(N.maisOK / df[,g], 2)
		# supplément précision dû aux transformations
		gP = round(N.maisOK / df[,t], 2)
		
		# rappel total
		R = round((df[,a] + N.maisOK) / df[,g], 2)
		# précision totale
		P = round((df[,a] + N.maisOK) / df[,t], 2)
		
		# on les colle direct à la fin de la table d'origine
		return (cbind(df, Rs, Ps, R, P))
	}
	# version simple pour les tables avec nmcols
	# (pour RPbarplot)
	else {
		R = round(df[,a] / df[,g], 2)  # rappel
		P = round(df[,a] / df[,t], 2)  # précision
		
		# on les colle direct à la fin de la table d'origine
		return (cbind(df, R, P))
	}
}




# RPbarplot(): Diagramme baton rappel précision côte à côte, par classes
# entrée = t(sortie de rplin [,2dernièrescol])
RPbarplot = function (tM, xlabel="Cas de figure", title="Rappel et précision", color=1, las.val=1) {
	n = ncol(tM)
	nclasses = nrow(tM)
	if (n < 2) {
		warning("Echec RBbarplot: (Géométrie attendue doit être comme la sortie de rplin : une table avec 2 dernières colonnes Rappel et Précision)")
		return(NULL)
	}
	RP.2cols = t(tM[,(n-1):n])
	
	if (color == 1) {
		colors=grey.colors(2)
	}
	if (color == 2) {
		# bleu clair (R), très clair (P)
# 		colors=c("#6593A0","#B9CCB8")
		# bleu foncé (R), jaune (P)
		colors=c("#0A2A3F","#FFEFA7")
	}
	# "#FFEFA7","#DB1522","#0A2A3F"
	
	# paramètrages légendes et taille de labels
	.pardefault <- par(no.readonly = T)  # on stocke les anciens params
	                                     # pour pouvoir les remettre

	mysize = 1
	if(ncol(tM) >= 8) { mysize = 0.8 }
	if(ncol(tM) >= 16) { mysize = 0.5 }
	if(ncol(tM) >= 32) { mysize = 0.3 }
	

	# pour les labels à la verticale
	if (las.val == 2) {
		# ajustement marge du bas selon label le + long
		maxchar=max(nchar(rownames(tM)))
		
		# marge du bas = 15 pour 60 caractères
		par(mar=c(as.integer(log(maxchar)*3),3,1,1))
	}
	
	legend_params = list(x="topright", bty = "n")

	# dessin proprement dit avec axe y invisible allant jusque 1,25 pour 
	chart = barplot(RP.2cols, beside=T, main=title, xlab=xlabel, legend=rownames(RP.2cols), ylim=c(0,1.25), args.legend = legend_params, axes=F, cex.names=mysize, col = colors, las = las.val)
	
	# axe y affiché : [0 à 1] gradué en dixièmes
	axis(2, at=(0:10/10), labels=(0:10/10))
	# labels dans chaque colonne (pos=1 veut dire juste en dessous de la position)
	text(x=as.vector(chart), y=as.vector(RP.2cols), labels=as.vector(RP.2cols), pos=3, cex=(3/5*dev.size()[1]/nclasses))
	
	par(.pardefault)
}

# Qbarplot(): Diagramme baton rappel ou précision, par classes
# entrée = sortie de rlin ou plin
Qbarplot = function (tM, xlabel="cas de figure", las.val=1) {
	n = ncol(tM)
	nclasses = nrow(tM)
	if (n < 2) {
		warning("Echec RBbarplot: (Géométrie attendue doit être comme la sortie de rplin : une table avec 2 dernières colonnes Rappel et Précision)")
		return(NULL)
	}
	Qcol = t(tM[,n])
	nom.col = colnames(tM)[n]
	type = "inconnu"
	if (nom.col == "R") {
		type = "Rappel"
		couleur = "#4D4D4D"
	}
	if (nom.col == "P") {
		type = "Précision"
		couleur = "#E6E6E6"
	}
	
	
	# paramètrages légendes et taille de labels
	.pardefault <- par(no.readonly = T)  # on stocke les anciens params
	                                     # pour pouvoir les remettre

	legend_params = list(x="topright", bty = "n")
	mysize = 1
	if(ncol(tM) >= 8) { mysize = 0.8 }
	if(ncol(tM) >= 16) { mysize = 0.5 }
	if(ncol(tM) >= 32) { mysize = 0.3 }
	

	# pour les labels à la verticale
	if (las.val == 2) {
		# ajustement marge du bas selon label le + long
		maxchar=max(nchar(rownames(tM)))
		
		# marge du bas = 15 pour 60 caractères
		par(mar=c(as.integer(log(maxchar)*3),3,1,1))
	}

	# dessin proprement dit avec axe y invisible allant jusque 1,25 pour 
	chart = barplot(Qcol, beside=T, xlab=paste(type,xlabel,sep="/"), ylim=c(0,1), args.legend = legend_params, cex.names=mysize, col=couleur, las=las.val)
	
	# labels dans chaque colonne (pos=1 veut dire juste en dessous de la position)
	text(x=as.vector(chart), y=Qcol, labels=Qcol, pos=3, cex=(3/5*dev.size()[1]/nclasses))
	
	par(.pardefault)
}

# variante de RPbarplot() pour les rplin.F contenant des diagnostics 'maisOK'
# ie: Diagramme baton rappel précision côte à côte, mais avec pour
# chacun un baton  "gain rappel" ou "gain précision" empilé
# entrée = t(sortie de rplin.F [,6dernièrescol])
RPbarplot.gain = function (tM, xlabel="Cas de figure", title="Rappel et précision", color=1, las.val=1) {
	tM = as.data.frame(tM)
	
	n = nrow(tM)
	
	# colonnes Rs, Ps, R, P sont toutes obligatoires
	if (is.null(tM$Rs) || is.null(tM$Ps) || is.null(tM$R) || is.null(tM$P)) {
		warning("Echec RBbarplot.gain: Géométrie attendue doit être comme la sortie de rplin.F : une table avec 4 dernières colonnes Rappel et Précision stricts (Rs, Ps), totaux (R,P)")
		return(NULL)
	}
	
	# choix des couleurs
	if (color == 1) {
		# gris sombre rappel, vert sombre gain rappel
		# blanc cassé précision, vert clair gain précision
		colors=c("#4D4D4D","#486648","#E6E6E6","#A4EAA4")
	}
	if (color == 2) {
		# à la obama poster
		# bleu clair (R), bleu foncé (gR), très clair (P), jaune (gP)
# 		colors=c("#6593A0","#0A2A3F","#B9CCB8","#FFEFA7")
		colors=c("#0A2A3F","#6593A0","#FFEFA7","#B9CCB8")
	}
	
	# paramètrages légendes et taille de labels
	.pardefault <- par(no.readonly = T)  # on stocke les anciens params
	                                     # pour pouvoir les remettre

	legend_params = list(x="topright", bty = "n")
	# pour les labels à la verticale
	if (las.val == 2) {
		# ajustement marge du bas selon label le + long
		maxchar=max(nchar(rownames(tM)))
		
		# marge du bas = 15 pour 60 caractères
		par(mar=c(as.integer(log(maxchar)*3),3,1,1))
	}
	
	# Préparation des données
	# ------------------------
	# On veut un barplot "empilé" (mesure stricte et gain) 
	# et "côte à côte" (rappel, précision) simultanément.
	# ----------------------------------------------------
	# Or barplot() ne permet pas cela en général...
	# ==> on en fait un empilé avec le gain (= mesure - mesure_stricte)
	#     mais en intercalant des (0, 0) dans les données pour qu'il
	#     n'y ait que deux données (et pas 4) dans chaque colonne
	myR0 = rbind(tM$Rs, tM$R-tM$Rs, 0, 0)
	my0P = rbind(0,0,tM$Ps, tM$P-tM$Ps)
	
	# l'objet interspersed.list contiendra ainsi n matrices de forme :
	# --------------------
	# | Rstrict |    0
	# --------------------
	# |  gainR  |    0
	# --------------------
	# |    0    | Pstrict
	# --------------------
	# |    0    |  gainP
	# --------------------
	interspersed.list=lapply(1:n,function(i,previous=null) {cbind(myR0[,i],my0P[,i])})
	
	# un équivalent de cbind sur le précédent ==> donne les données pour barplot
	toplot = matrix(unlist(interspersed.list),ncol=2*n)
	
	rownames(toplot) = c('rappel strict', 'gain rappel', 'précision stricte', 'gain précision')
	
	# ICI dessin des barres
	chart = barplot(toplot, space=c(1,0), main=title, xlab=xlabel, ylim=c(0,1.25), args.legend = legend_params, axes=F, col = colors)
	
	# axe X affiché : noms des cas de figures placés aux milieux entre chaque groupe de 2 barres
	middleX=colSums(matrix(chart,nrow=2))/2
	axis(1, at=middleX, labels = rownames(tM), tick=F, las=las.val, cex=.8)
	
	# axe y affiché : [0 à 1] gradué en dixièmes
	axis(2, at=(0:10/10), labels=(0:10/10))
	
	# labels rouges barres du dessous (Rappel strict et Précision stricte)
	text(x=as.vector(chart), y=as.vector(rbind(tM$Rs,tM$Ps)), labels=as.vector(rbind(tM$Rs,tM$Ps)), pos=1, col="#DB1522", cex=(2/5*dev.size()[1]/n))
	
	# labels du total en haut (Rappel strict + gain rappel et Précision stricte + gain précision)
	text(x=as.vector(chart), y=as.vector(rbind(tM$R,tM$P)), labels=as.vector(rbind(tM$R,tM$P)), pos=3, cex=(3/5*dev.size()[1]/n))
	
	# légende avec les 4 couleurs
	legend(x="topright", bty="n", legend=rownames(toplot), fill=colors, ncol=2)
	
	par(.pardefault)
}


# l'entrée est une table en % colonnes sans totaux mais sur [0:100]
# par exemple 100*pccol(table(t$typobib_clu4, t$pdfver))
PCbarplot = function (PCCOL, col.names="X", addpc=T,color=1, las.val=1) {
	
	if (color == 1) {
		# obama
		colors=c("#FFEFA7","#6593A0","#DB1522","#B9CCB8","#0A2A3F")
	}
	if (color == 2) {
		# warm
		colors=c("#334D5C","#EFC94C","#DF5A49","#45B29D","#E27A3F","#FFEFA7","#6593A0","#DB1522","#B9CCB8","#0A2A3F")
	}
	if (color == 3) {
		# ajustable
		colors=topo.colors(nrow(PCCOL))
	}
	if (color == 4) {
		# japan garden
		colors=c("#990000","#F0ED9C","#7C9F87","#00223D","#276E60")
	}
	if (color == 5) {
		# aerial summer
		colors=c("#122129","#D9B53F","#4D6E80","#F1D679","#F2E2AA")
	}
	if (color == 6) {
		# terrain colors (n illimité)
		colors=terrain.colors(nrow(PCCOL))
	}
	if (color == 7) {
		# idem dans l'autre sens
		colors=rev(terrain.colors(nrow(PCCOL)))
	}
	
	# inclinaison des labels de chaque barre (ie axe X)
	# => directement dans las.val
	
	# supprimer totaux colonnes (s'ils sont présents)
	if (rownames(tail(PCCOL, n=1)) == "TOTAL") {
		# tout sauf la dernière ligne
		PCCOL = head(PCCOL, n=-1)
	}
	
	# paramètres
	legend_params = list(x="topright", bty = "n")
	mysize = 1
	if(ncol(PCCOL) >= 8) { mysize = 0.8 }
	if(ncol(PCCOL) >= 16) { mysize = 0.5 }
	if(ncol(PCCOL) >= 32) { mysize = 0.3 }
	
	.pardefault <- par(no.readonly = T)
	if (las.val == 2) {
		# ajustement marge du bas selon label le + long
		maxchar=max(nchar(colnames(PCCOL)))
		
		# marge du bas = 20 pour 60 caractères
		par(mar=c(as.integer(log(maxchar)*3),3,1,1))
	}
	
	# dessin de base
	chart = barplot(PCCOL, xlab=col.names, ylab="%", legend=rownames(PCCOL), args.legend=legend_params, ylim=c(0,125), axes=F, col=colors, cex.names=mysize, space=0.5, las=las.val)
	
	# axe y affiché : [0 à 100] gradué en quarts
	axis(2, at=(0:4*25), labels=(0:4*25), cex.axis=1.5)
	

	
	# valeurs à ajouter comme labels
	if (!addpc) {
		meslabels = as.vector(PCCOL)
	}
	else {
		# idem en y collant le caractère '%'
		meslabels = paste(sep="", as.vector(PCCOL),rep("%",length(PCCOL)))
	}

	# positions (x,y) des labels sur chaque barre
	# --------------------------------------------
	# position horizontale de chaque plot (contenue dans la valeur renvoyée par barplot)
	# reproduite par le nombre de labels par plots
	xvals = rep(chart,each=nrow(PCCOL))
	# position verticale du haut de chaque segment
	ytops = apply(PCCOL,2,cumsum)
	# on prepend une ligne de 0
	ybottoms = rbind(rep(0,ncol(PCCOL)),ytops)
	# et on enlève la dernière ligne (celle des maxima)
	ybottoms = ybottoms[1:(nrow(ybottoms)-1),]
	# et enfin le label vient au milieu entre le haut et le bas du segment
	yvals=(ytops + ybottoms)/2

	# ajout des labels
	text(xvals, as.vector(yvals), labels=meslabels, cex=mysize)
	
	# restaurer la valeur des paramètres
	par(.pardefault)
}

table.rm0 = function (colA, colB) {
	nullardos = names(which(rowSums(table (colA,colB)) == 0))
	return(table (colA,colB, exclude=nullardos, deparse.level=0))
}

table2df = function(tab, marginsums=0) {
	mes.cols = colnames(tab)
	mes.rows = rownames(tab)
	Nrow = nrow(tab)
	df = data.frame(matrix(as.numeric(tab),nrow = Nrow))
	colnames(df) = mes.cols
	rownames(df) = mes.rows
	if (1 %in% marginsums) {
		df = rbind(df,TOT=colSums(df))
	}
	if (2 %in% marginsums) {
		df = cbind(df,TOT=rowSums(df))
	}
	return(df)
}

# (le niveau doc correspond à des stats en plus sur une table optionnelle doctable)
varstats = function(varname="pdfver", bibtable=gt, niveau="bib", doctable=pardoc) {
	# EXEMPLE
	# > varstats (varname="pdfver", niveau="doc")
	# --------------------------------------------
	#   pdfver nDocs nBibs nChamps nAuteurs
	# 1    1.2    27  1158    7600     4482
	# 2    1.3   909 41154  265710   132221
	# 3    1.4   760 34913  233381   100819
	# 4    1.5    79  2941   19803     9373
	# 5    1.6   148  7597   52435    25255
	# 6    1.7     4   356    2482      495

	if (niveau == "doc") {
		k = which(colnames(doctable) == varname)
		nD = as.data.frame(table (doctable[,k]))
		colnames(nD) = c(varname, 'nDocs')
	}
	k = which(colnames(bibtable) == varname)
	
	# cas d'erreur si  varname n'existe pas
	if (length(k) == 0) {
		warning(paste("Echec varstats: la variable $", varname,"est absente du tableau des refbibs "))
		return(NULL)
	}
	
	# dans tous les cas doc et bib
	nB = as.data.frame(table (bibtable[,k]))
	colnames(nB) = c(varname, 'nBibs')
	nCh = aggregate(as.numeric(bibtable$gfields), by=list(bibtable[,k]), FUN=sum)
	colnames(nCh) = c(varname,'nChamps')
	nAu = aggregate(as.numeric(bibtable$gnames), by=list(bibtable[,k]), FUN=sum)
	colnames(nAu) = c(varname,'nAuteurs')
	if (niveau == "doc") {
		stats.sortie = merge(nD,nB, by=varname)
		stats.sortie = merge(stats.sortie,nCh, by=varname)
		stats.sortie = merge(stats.sortie,nAu, by=varname)
	}
	else {
		stats.sortie = merge(nB,nCh, by=varname)
		stats.sortie = merge(stats.sortie,nAu, by=varname)
	}
	
	# passage de la colonne 1 en rownames
	rownames(stats.sortie) = stats.sortie[,1]
	stats.sortie = stats.sortie[,-1]
	
	return(stats.sortie)
}
