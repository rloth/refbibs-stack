#! /bin/bash

# (Descriptions libres du run)
export MY_NEW_SAMP=$1       # ex: "seg-a-40" ou "vanilla"
export MODEL_type=$2        # ex: "segmentation" ou "none"

# (Dirs)
# grobid annotation tool
export GB="/home/loth/refbib/grobid"
export GB_NAME="g033d"
export GB_GIT_ID=`git --git-dir=$GB/.git log --pretty=format:'%h' -n1`

# (Corpus d'évaluation)
export CORPUS_NAME="BI-10kELS-s1"
export CORPUS_SHORTNAME="s1"

# (Où et qui)
# structured backup for results
export CoLTrAnE="/home/loth/refbib/analyses/coltrane"
export CRFTRAINEDID=${GB_NAME}_${MY_NEW_SAMP}
export EVALID=${CORPUS_SHORTNAME}-${GB_NAME}_${MY_NEW_SAMP}

# a new home
export NEWDIR=${CoLTrAnE}/eval/${CORPUS_SHORTNAME}-${GB_NAME}_avec_${MY_NEW_SAMP}
export OUTDIR="$NEWDIR/TEI-back_done"   

echo "$MY_NEW_SAMP / $MODEL_type [$GB] / outdir:$OUTDIR"

# (Paramètres de balisage)

# dossier gold pour eval xml
export EXF="/home/loth/refbib/corpus/bibistex/05_docs/s1/C-xmls_flat/"

# dossier à baliser pdf
export EPF="/home/loth/refbib/corpus/bibistex/05_docs/s1/A-pdfs_flat/"

# nombre de proc au balisage
export NCPU=4

# === === === === === === === === === === === ===
# 1 - DOSSIER NOUVELLE EVAL

mkdir -p $NEWDIR
cd $NEWDIR

# récupération à l'arrache de tout descriptif *readme ou *log du sample
if [ -f ../../samp/$MY_NEW_SAMP/meta/*readme ] ;
  then ln -s ../../samp/$MY_NEW_SAMP/meta/*readme description_${MY_NEW_SAMP}.readme ;
fi

if [ -f ../../samp/$MY_NEW_SAMP/meta/*log ] ;
  then ln -s ../../samp/$MY_NEW_SAMP/meta/*log description_${MY_NEW_SAMP}.log ;
fi

# === === === === === === === === === === === ===
# 2 - SUBSTITUTION "MODEL_typeE RESULTANT" CHEZ GROBID-HOME
#
# rien à faire : si on vient d'entraîner le modèle est dans
#                son dossier gb-home (et stocké dans coltrane/run)
#

# === === === === === === === === ===
# 3 - LANCEMENT DU BALISAGE

# lancement service  # # # # #  1/2
pushd $GB/grobid-service/
mvn -Djava.io.tmpdir="/run/shm/mon_grobid_tmp/" jetty:run-war &
SERVICE_PID=$!
sleep 30 # parfois il essaye de D/L qqch
popd

# avant de baliser
mkdir -p $OUTDIR

# on fait la todolist
ls $EPF/ > temp.docs.ls   # todo: timestamp

split -n $NCPU temp.docs.ls

# lancement client # # # # # # 2/2
PIDS=()
i=0
for liste in xa* ;
  do client_passe_liste.sh < $liste 2>> clients.curl.log & PIDS[$i]=$! ;
     i=$((i+1)) ;
 done

for pid in ${PIDS[*]} ; do echo "PID $pid en cours de balisage" ; done

# ça tourne... on attend le premier puis les suivants
for pid in ${PIDS[*]};  do wait $pid ; echo "PID $pid a fini" ; done

# nettoyages
# /!\ 
rm -fr xa*

kill $SERVICE_PID

# === === === === === === === === ===
# 4 - ENFIN EVAL ELLE-MËME !
 
eval_xml_refbibs.pl -r $EXF -x $OUTDIR -g 'elsevier' \
1> gb_eval_${EVALID}.tab \
2> gb_eval_${EVALID}.log

evalpid=$!

echo "${EVALID} en cours"
wait evalpid
# watch "tail -n 42 gb_eval_$EVALID.log"
echo "fini!"
