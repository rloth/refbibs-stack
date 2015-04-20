#! /bin/bash

export eps=$1        #  ex: "e-5"
export GB=$2         #  ex: "/home/loth/refbib/grobid"

# remplacement de la variable epsilon de wapiti dans la src de grobid
cp $GB/grobid-trainer/alternative_wapiti_config/WapitiTrainer.${eps}.java $GB/grobid-trainer/src/main/java/org/grobid/trainer/WapitiTrainer.java

# recompilation
cd $GB/grobid-trainer
mvn -Dmaven.test.skip=true clean compile install

# voilà !
