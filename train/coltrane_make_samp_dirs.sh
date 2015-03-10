#! /bin/bash

# (Descriptions libres)
export MY_NEW_SAMP=$1       # ex: "seg-a-40"
export MODEL_type=$2       # ex: "segmentation"

# result's structured backup => "coltrane" dir
export CoLTrAnE="/home/loth/refbib/analyses/coltrane"

export ORIG_DATASET="/home/loth/refbib/grobid/grobid-trainer/resources/dataset"

export SAMP_PATH=$CoLTrAnE/samp/$MY_NEW_SAMP

# === === === === === === === === === ===
# CONSTITUTION DU SAMPLE
mkdir -p $SAMP_PATH/data
mkdir -p $SAMP_PATH/meta
cd $SAMP_PATH

mkdir -p data/$MODEL_type

# --- (corpus tei et raw) ---
# la suite est "do it yourself"
# DIY ----- DIY ----- DIY ----- DIY ----- DIY ----- DIY -----

# par exemple en provenance des corpus actuels de Patrice
	# ajout tel quel des données d'entraînement pré-existantes tei + raw
	# cp -r $ORIG_DATASET/${MODEL_type}.bak/corpus data/$MODEL_type/.

# et/ou depuis les stocks créés exprès
	# cp ~/refbib/corpus/trainbibistx/${MODEL_type}/training.*.raw/* data/${MODEL_type}/corpus/raw/.
	# cp ~/refbib/corpus/trainbibistx/${MODEL_type}/training.*.tei/* data/${MODEL_type}/corpus/tei/.

# si il faut faire des f-flux raw:
# --------------------------------
# grobid annotation tool
export GB="/home/loth/refbib/grobid"
# new training docs
export exemples_prets=~/refbib/corpus/trainbibistx/segmentation/pdfs
# 1/3 - obtention: nom de l'executable de pretraining dans le jar
case $MODEL_type in
fulltext*)
  pre_MODEL='createTrainingFulltext'
  ;;
segmentation)
  pre_MODEL='createTrainingSegmentation'
  ;;
reference-segmenter)
  pre_MODEL='createTrainingReferenceSegmentation'
  ;;
citation)
  pre_MODEL='createTrainingFulltext'
  ;;
name/citation)
  pre_MODEL='createTrainingFulltext'
  ;;
*)
  pre="type de modèle grobid inconnu:'$MODEL_type'"
  ;;
esac

# createTraining (f-flux <= pdf) /!\ attention créer un regard
java -Xmx2G -jar $GB/grobid-core/target/grobid-core-*.one-jar.jar -gH $GB/grobid-home -gP $GB/grobid-home/config/grobid.properties -dIn ${exemples_prets} -dOut trainers.${MODEL_type}.praws/ -exe ${pre_MODEL}


# 2/3 génération et 3/3 récup
# cf. samp/seg-a-40_flux_anciens_g030/meta/préparation.training.*.readme

# --- (autres fichiers) ---
# on ajoute les dossiers qu'on ne modifiait pas en provenance des corpus actuels
cp -r $ORIG_DATASET/${MODEL_type}.bak/crfpp-templates $SAMP_PATH/data/$MODEL_type/.
cp -r $ORIG_DATASET/${MODEL_type}.bak/evaluation $SAMP_PATH/data/$MODEL_type/.

echo "ok dirs created"
tree $SAMP_PATH
