#! /bin/bash

# (Descriptions libres)
export MY_NEW_SAMP=$1       # ex: "seg-a-40"
export MODEL_type=$2       # ex: "segmentation"
export with_previous=${3:-anyvalue_except_no_previous}

# result's structured backup => "coltrane" dir
export CoLTrAnE="/home/loth/refbib/analyses/coltrane"

export ORIG_DATASET="/home/loth/refbib/grobid/grobid-trainer/resources/dataset"

export SAMP_PATH=$CoLTrAnE/samp/$MY_NEW_SAMP

# === === === === === === === === === ===
# CONSTITUTION DU SAMPLE
mkdir -p $SAMP_PATH/data
mkdir -p $SAMP_PATH/meta

cd $SAMP_PATH
# plongeoir à corpus: lien symbq instanciable, vers l'intérieur de data
#~ ln -s $SAMP_PATH/data/$MODEL_type/corpus/tei corpus # (ne pointe encore nulle part)

mkdir -p $SAMP_PATH/data/$MODEL_type

# --- (corpus tei et raw) ---

mkdir data/$MODEL_type/corpus

# la suite est "do it yourself"
# DIY ----- DIY ----- DIY ----- DIY ----- DIY ----- DIY -----
# par exemple en provenance des corpus actuels de Patrice
	# ajout tel quel des données d'entraînement pré-existantes tei + raw
	# cp -r $ORIG_DATASET/${MODEL_type}.bak/corpus data/$MODEL_type/.

# et/ou depuis les stocks créés exprès
	# cp ~/refbib/corpus/trainbibistx/${MODEL_type}/training.*.raw/* data/${MODEL_type}/corpus/raw/.
	# cp ~/refbib/corpus/trainbibistx/${MODEL_type}/training.*.tei/* data/${MODEL_type}/corpus/tei/.


# 2/3 génération et 3/3 récup
# cf. samp/seg-a-40_flux_anciens_g030/meta/préparation.training.*.readme

# --- (autres fichiers) ---
# on ajoute les dossiers qu'on ne modifiait pas en provenance des corpus actuels
if [ -d $ORIG_DATASET/${MODEL_type}.bak ] ;
  then cp -r $ORIG_DATASET/${MODEL_type}.bak/crfpp-templates $SAMP_PATH/data/$MODEL_type ;
  cp -r $ORIG_DATASET/${MODEL_type}.bak/evaluation $SAMP_PATH/data/$MODEL_type ;
  else cp -r $ORIG_DATASET/${MODEL_type}/crfpp-templates $SAMP_PATH/data/$MODEL_type ;
  cp -r $ORIG_DATASET/${MODEL_type}/evaluation $SAMP_PATH/data/$MODEL_type ;
fi

# --- (autres fichiers) ---
# sauf exception on ajoute aussi tous les fichiers d'entraînement initiaux
if [ $with_previous != "no_previous" ] ;
  then cp -r $PREVIOUS_FULLEST_DATASET/${MODEL_type}/corpus $SAMP_PATH/data/$MODEL_type/.
fi

echo "ok dirs created"
tree $SAMP_PATH
