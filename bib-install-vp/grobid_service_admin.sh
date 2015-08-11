#!/bin/bash
### BEGIN INIT INFO
# Provides:          grobid
# Short-Description: start/stop grobid annotation server
### END INIT INFO

# ------------------------------==============
# lancement | arrêt | statut de grobid-service
# ------------------------------==============
# (c) 2015 INIST/CNRS romain.loth@inist.fr
#     [projet ISTEX - ANR-10-IDEX-0004-02]
#
# Outil commandé: "Grobid" de Patrice Lopez
#        cf. http://grobid.readthedocs.org/
#


## prérequis : le dossier de grobid dans GB
if [ -z "$GROBID_HOME" ]; then
    echo -e "La variable d'environnement \$GROBID_HOME n'est pas fixée.\nVeuillez la créer et lui donner comme valeur le chemin du dossier de grobid."
    exit 1
fi

GB=$GROBID_HOME

## diagnostic préalable : simple grep sur la liste des processus
mes_pids=`ps -Af | grep "java.*grobid.*jetty:run-war" | grep -v "grep" | tr -s ' ' | cut -f2 -d' '`

nb_pids=`wc -w <<< $mes_pids`

case $nb_pids in
	0)
		running=false
		problem=false
		;;
	1)
		running=true
		problem=false
		GB_PID=$mes_pids
		;;
	*)
		running=true
		problem=true
		;;
esac

if [ $problem == true ] ;
	then 
	echo "Le service grobid semble déjà lancé *plusieurs* fois ($nb_pids): situation à régler à la main (PIDS recensés: $mes_pids)"
	exit 1
fi

## actions
case $1 in
	start)
		if [ $running != true ]
			then
			cd $GB/grobid-service
			
			# choix normal (plus lent mais prend moins de RAM)
			# --------------------------------------------------------
			# nohup mvn jetty:run-war & echo $! > ~/grobid-service.pid &
			
			
			# choix optimisé (si beaucoup de RAM)
			# -----------------------------------------
			nohup mvn -Djava.io.tmpdir="/run/shm/mon_grobid_tmp/" jetty:run-war & echo $! > ~/grobid-service.pid &
			# (supplément à la RAM moyenne utilisée = Nombre de CPU faisant le traitement X la taille moyenne d'un PDF traité X 2)
			
			cd ~
			export GB_PID=`cat grobid-service.pid`
			echo "Service grobid lancé via Jetty sur PID $GB_PID"
			exit 0
		else
			echo "Service grobid déjà lancé (PID $GB_PID)"
			exit 1
		fi
		;;
	stop)
		if [ $running == true ]
			then
			kill $GB_PID
			rm -fr ~/grobid-service.pid
			echo "Service grobid (PID $GB_PID) stoppé !"
			exit 0
		else
			echo "Service grobid déjà inactif"
			exit 1
		fi
		;;
	cacheclean)
		if [ $running != true ]
			then
			# cacheclean: a priori il le fait tout seul sauf
			#             si pdftoxml a crashé (gros pdf)
			# todo: variable tempdir
			rm -fr /run/shm/mon_grobid_tmp/*
			exit 0
		else
			echo "Le service grobid ($GB_PID) doit être stoppé avant de nettoyer le cache"
			exit 1
		fi
		;;
	status)
		if [ $running == true ]
			then
			echo "Service grobid is running (PID $GB_PID)"
			exit 0
		else
			echo "Service grobid inactif"
			exit 0
		fi
		;;
	*)
		echo "Usage: grobid_service_admin.sh {start|stop|cacheclean|status}"
		exit 1
		;;
esac
