#! /bin/bash

export OUTDIR="TEI-back_done"
export EPF="/home/loth/refbib/corpus/bibistex/05_docs/s1/A-pdfs_flat"


while read pdfdocpath ;
	do tgt=`echo $pdfdocpath | sed 's/\.pdf$/.tei.xml/ ; s!/data/!!' | tr "/ ()," "_"`
	
	# appel du service  # # # # # # # # # # # # # # # # # # # # # # # # 2/2
	curl --form input=@$EPF/$pdfdocpath 127.0.0.1:8080/processReferences > $OUTDIR/${tgt} ;
	done
