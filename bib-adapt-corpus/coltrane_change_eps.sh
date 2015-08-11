#! /bin/bash

export eps=$1        #  ex: "e-5"
export GB=$2         #  ex: "/home/loth/refbib/grobid"

export trainer_src="$GB/grobid-trainer/src/main/java/org/grobid/trainer/WapitiTrainer.java"

# remplacement de la variable epsilon de wapiti dans la src de grobid
cp $GB/grobid-trainer/alternative_wapiti_config/WapitiTrainer.${eps}.java ${trainer_src}

# recompilation
cd $GB/grobid-trainer
mvn -Dmaven.test.skip=true clean compile install

# voilà !


##### préparer les alternatives (une seule fois, à partir de l'original)
#~ cd $GB/grobid-trainer
#~ mkdir alternative_wapiti_config
#~ 
#~ # l'original à e-5
#~ cp -rp ${trainer_src} alternative_wapiti_config/WapitiTrainer.e-5.java
#~ 
#~ # version e-4
#~ sed 's/= 0.00001;/= 0.0001;/' < ${trainer_src} > alternative_wapiti_config/WapitiTrainer.e-4.java
#~ 
#~ # version e-3
#~ sed 's/= 0.00001;/= 0.0001;/' < ${trainer_src} > alternative_wapiti_config/WapitiTrainer.e-3.java
