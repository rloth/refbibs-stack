#! /bin/bash
################################################
# Installation d'une VP grobid pour istex-bibs #
#----------------------------------------------#
# 04/03/2015   (c) CNRS   romain.loth@inist.fr #
#----------------------------------------------#
# projet ISTEX            ANR-10-IDEX-0004-02  #
################################################
#   Outil déployé: "Grobid" de Patrice Lopez   #
# cf. http://grobid.readthedocs.org/en/latest/ #
################################################

# Dépôt du fork istex de grobid
export MON_DEPOT="https://codeload.github.com/rloth/grobid/tar.gz/istex-bib-stable"
export DIR_CIBLE="grobid-istex"

# Préalables
# ==========
# variables d'environnement INIST
# --------------------------------
if ! grep -q "istex-bib"  ~/.bashrc ;
  then echo '# section specifique pour istex-bib'                 >> ~/.bashrc ;
       echo 'export http_proxy="http://proxyout.inist.fr:8080"'   >> ~/.bashrc ;
       echo 'export https_proxy="https://proxyout.inist.fr:8080"' >> ~/.bashrc ;
       echo "export GB=$DIR_CIBLE" >> ~/.bashrc ;
       source ~/.bashrc
fi

# paquets maven
# -------------
# une jdk >= 7 et maven sont essentiels pour compiler grobid
sudo apt-get install openjdk-7-jdk   # ou inist-oracle-jdk8 ?
sudo apt-get install maven

# espace temporaire dédié dans la RAM
# ------------------------------------
mkdir -p /run/shm/mon_grobid_tmp
rm -fr /run/shm/mon_grobid_tmp/*

# récupération de la version testée
# ---------------------------------
# tarball     ?? TODO rendre possible git clone ??
curl $MON_DEPOT > grobid.tgz

# /!\ crée un dossier nommé "grobid-istex"
mkdir -p $DIR_CIBLE
tar -xzvf grobid.tgz -C $DIR_CIBLE --strip-components 1


# Installation/Compilation
# =========================
# Création d'un .m2/settings.xml ad hoc
echo "<settings>
  <!-- mon proxy inist -->
  <proxies>
   <proxy>
      <active>true</active>
      <protocol>http</protocol>
      <host>proxyout.inist.fr</host>
      <port>8080</port>
      <nonProxyHosts>*.inist.fr|*.istex.fr</nonProxyHosts>
    </proxy>
  </proxies>
  
  <!-- Profil pour pouvoir ajouter un repo -->
  <profiles>
    <profile>
      <id>Profil avec central.maven.org</id>
      <activation>
        <activeByDefault>true</activeByDefault>
      </activation>
      <repositories>
        <repository>
          <id>central.maven</id>
          <name>central.maven.org Repository</name>
          <url>http://central.maven.org/maven2/</url>
          <layout>default</layout>
          <releases><enabled>true</enabled><updatePolicy>never</updatePolicy></releases>
          <snapshots><enabled>true</enabled><updatePolicy>never</updatePolicy></snapshots>
        </repository>
      </repositories>
    </profile>
  </profiles>
</settings>
" > ~/.m2/settings.xml

# build
# -------
mvn -Dmaven.test.skip=true clean compile install

# Lancement du service
# =====================
cd $DIR_CIBLE/grobid-service
nohup mvn -Djava.io.tmpdir="/run/shm/mon_grobid_tmp/" jetty:run-war & echo $! > ~/grobid-service.pid &
cd ~
export GB_PID=`cat grobid-service.pid`
echo "Service grobid lancé via Jetty sur PID $GB_PID"
