#! /bin/bash

for i in `seq 2 9` ; do echo methode-$((i-2)) ; cat mes_50.eval_out.d/*.tsv | grep -v "^bid" | cut -f$i | sort | uniq -c ; done

