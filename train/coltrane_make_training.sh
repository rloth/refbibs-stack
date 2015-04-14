#! /bin/bash

# (Descriptions libres)
export MY_NEW_SAMP=$1       # ex: "seg-a-40"
export MODEL_type=$2        # ex: "segmentation"
export GB_BASENAME=$3       # ex: "g033f"
export eps="e-5"

# (Dirs)
# grobid annotation tool
export GB="/home/loth/refbib/grobid"
export GB_NAME=${GB_BASENAME}.${eps}
export GB_GIT_ID=`git --git-dir=$GB/.git log --pretty=format:'%h' -n1`


# result's structured backup => "coltrane" dir
export CoLTrAnE="/home/loth/refbib/analyses/coltrane"
export CRFTRAINEDID=${GB_NAME}_${MY_NEW_SAMP}

export SAMP_PATH=$CoLTrAnE/samp/$MY_NEW_SAMP


# === === === === === === === === === ===
# 0 - obtention nom de la cible maven
case $MODEL_type in
fulltext*)
  tgt='train_fulltext'
  ;;
segmentation)
  tgt='train_segmentation'
  ;;
reference-segmenter)
  tgt='train_reference-segmentation'
  ;;
citation)
  tgt='train_citation'
  ;;
name/citation)
  tgt='train_name_citation'
  ;;
*)
  tgt="type de modèle grobid inconnu:'$MODEL_type'"
  ;;
esac


# === === === === === === === === === ===
# 1 - ENSUITE SUBSTITUTION CHEZ GROBID
cd $GB/grobid-trainer/resources/dataset
if [ ! -d $MODEL_type.bak ]
 then cp -rp $MODEL_type $MODEL_type.bak
fi
rm -fr $MODEL_type
ln -s $SAMP_PATH/data/$MODEL_type $MODEL_type

# === === === === === === === === ===<  <<  <  <<  <  <<
# 2 - PUIS LANCEMENT PROPREMENT DIT   <  <<  <  <<  <  <<
cd $GB/grobid-trainer
export LC_ALL=C  # finalement semble encore nécessaire

export MAVEN_OPTS="-Xmx12G"
mvn generate-resources -P ${tgt} \
1> $MY_NEW_SAMP.$eps.trainer.mvn.log \
2> $MY_NEW_SAMP.$eps.trainer.crf.log 

# ça tourne...

# === === === === === === ===
# 3 - RECUP MODELE ET LOG
mkdir -p $CoLTrAnE/run/$CRFTRAINEDID/model/$MODEL_type
cp -p $GB/grobid-home/models/$MODEL_type/model.wapiti $CoLTrAnE/run/$CRFTRAINEDID/model/$MODEL_type/.

# logs
mkdir -p $CoLTrAnE/run/$CRFTRAINEDID/log
mv -v $MY_NEW_SAMP.$eps.trainer.mvn.log $CoLTrAnE/run/$CRFTRAINEDID/log/.
mv -v $MY_NEW_SAMP.$eps.trainer.crf.log $CoLTrAnE/run/$CRFTRAINEDID/log/.


# === === === === ===
# 4 - envoi infos
RUN_INFO=`grep -P "\[INFO\] (Total|Finished)" < $CoLTrAnE/run/$CRFTRAINEDID/log/$MY_NEW_SAMP.trainer.mvn.log`
FILE_INFO=`ls -lhGF --time-style long-iso $GB/grobid-home/models/$MODEL_type/model.wapiti`

# 2 x un mail avec toutes les infos clés et le déroulement du CRF
# => @gmail et @inist
echo -e "subject:voilà voilà:fini $MODEL_type sur $MY_NEW_SAMP\nfrom:training_machine\n$RUN_INFO\n\n$FILE_INFO\n\n:)\n\n" > temp_debut_mail
cat temp_debut_mail $CoLTrAnE/run/$CRFTRAINEDID/log/$MY_NEW_SAMP.trainer.crf.log | sendmail "romain.loth@gmail.com,romain.loth@inist.fr"

# voilà :)
