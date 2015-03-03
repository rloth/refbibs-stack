#! /bin/bash

# (Descriptions libres)
export MY_NEW_SAMP=$1       # ex: "seg-a-40" ou "seg-c-40PL"
export CORPUS_NAME="BI-10kELS-s1"

export MODEL_type=$2        # ex: "segmentation"


# (Dirs)
# home
export ANALYSES="/home/loth/refbib/analyses"
export OUTDIR="TEI-back_done"   
# ou l'inamovible:
# OUTDIR=/home/loth/refbib/grobid/TEI_done_local/

# dossier gold pour eval xml
export EXF="/home/loth/refbib/corpus/bibistex/05etc/10b_XMLs_flat"
# dossier à baliser pdf
export EPF="/home/loth/refbib/corpus/bibistex/05etc/05_PDFs_flat-TOUS"


# grobid annotation tool
export GB="/home/loth/refbib/grobid"
export GB_NAME="g033c"

# result's structured backup
export CoLTrAnE="/home/loth/refbib/analyses/coltrane"
export CRFTRAINEDID=${GB_NAME}_${MY_NEW_SAMP}


# === === === === === === === === === === === ===
# 1 - DOSSIER NOUVELLE EVAL

cd $ANALYSES

# new id for analyses/dir
NUMERO=`echo $(($(ls | cut -d'-' -f1 | sort -n | tail -n1) + 1))`

NEWDIR=${NUMERO}-${CORPUS_NAME}-${GB_NAME}_avec_${MY_NEW_SAMP}

mkdir $NEWDIR
cd $NEWDIR

# TODO remplacer par ln -s $CoLTrAnE/samp/seg-a+c-80/meta/descri.log
touch description_${MY_NEW_SAMP}.log  # todo remplir les infos

# === === === === === === === === === === === ===
# 2 - SUBSTITUTION "MODEL_typeE RESULTANT" CHEZ GROBID-HOME
cd $GB/grobid-home/models/$MODEL_type
# ll
#        -rw-rw-r-- 1 loth 3,0M 2015-02-10 15:49 MODEL_type.wapiti
#        -rw-rw-r-- 1 loth 3,8M 2015-02-10 11:27 MODEL_type.wapiti.old
#        -rw-rw-r-- 1 loth 5,3M 2015-02-10 11:35 MODEL_type.wapiti.seg-a-40
#~ cp MODEL_type.wapiti MODEL_type.wapiti.precedent.monbak
cp MODEL_type.wapiti.$MY_NEW_SAMP MODEL_type.wapiti

# question: a-t-on ce modèle en stock ?
if [-f $CoLTrAnE/run/$CRFTRAINEDID/model/MODEL_type.wapiti]
  then
    # on sait jamais
    cp -p MODEL_type.wapiti ancien.MODEL_type.wapiti
    # overwrite
    rm -f MODEL_type.wapiti
    # récup de la sauvegarde "CRF paramétré" générée par batch_train.sh
    cp -p $CoLTrAnE/run/$CRFTRAINEDID/model/MODEL_type.wapiti ./MODEL_type.wapiti
fi

# === === === === === === === === ===
# 3 - LANCEMENT DU BALISAGE

# on retourne
cd $ANALYSES/$NEWDIR

mkdir $OUTDIR

# à l'ancienne (choix inactif)
# -------------
# alias grobid='java -jar /home/loth/refbib/grobid/grobid-core/target/grobid-core-*.one-jar.jar -gH /home/loth/refbib/grobid/grobid-home/ -exe processReferences'

# grobid -dIn $EPF -dOut $OUTDIR/

# en service REST local (choix actif)
# ----------------------
# lancement service  # # # # # # # # # # # # # # # # # # # # # 1/2
pushd $GB/grobid-service/
mvn jetty:run-war &
sleep 30 # parfois il essaye de D/L qqch
popd

# on fait la todolist
ls $EPF/ > temp.docs.ls   # todo: timestamp
total_nom=`wc -l temp.docs.ls` ;
compteur=0 ;
#~ for doc in `shuf temp.docs.ls | head -n 500`
for doc in `cat temp.docs.ls` ;
	do compteur=$((compteur+1)) ;
	tgt=`echo $doc | sed 's/\.pdf$/.tei.xml/ ; s!/data/!!' | tr "/ ()," "_"`
	
	# appel du service  # # # # # # # # # # # # # # # # # # # # # # # # 2/2
	curl --form input=@$EPF/$doc 127.0.0.1:8080/processReferences > $OUTDIR/${tgt} ;
	# log dans la sortie ou dans nohup
	if mille=`echo $compteur | grep 000$` ; 
		then echo -e "\n\n\n---------------------------------------------------\n  grobid-service en cours : $compteur / $total_nom\n---------------------------------------------------\n\n\n" ;
	fi
done

# ça tourne...

# === === === === === === === === ===
# 4 - ENFIN EVAL ELLE-MËME !
 
eval_xml_refbibs.pl -r $EXF -x $OUTDIR -g 'elsevier' \
1> gb_eval_${NUMERO}.tab \
2> gb_eval_${NUMERO}.log

# eval_xml_refbibs.pl -r /home/loth/refbib/corpus/bibistex/05etc/10_XMLs_flat -x TEI-back_done -g elsevier -c
