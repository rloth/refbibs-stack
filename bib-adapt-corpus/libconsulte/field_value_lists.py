#! /usr/bin/python3
"""
A set of ranges for dates: *-1959, 1960-79, 1980-89, 1990-99, 2000-*
 +
Hardcoded lists of values for 3 ISTEX API fields:
 - language
 - categories.wos
 - genre

why?
-----
The fields are often used as representativity criteria (the counts for
each of their values can be used as quotas for a proportional sample)

NB
---
The values-lists could be retrieved by a terms facet aggregation but the
API truncates them at count 10... Unless something changes, we'll store
a simplified copy here.        (Last copy from API + pruning 15/07/2015)
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# ----------------------------------------------------------------------
# 4 document classification criteria => 4 schemes
#
#           3 lists of constants : LANG, GENRE, SCICAT
#           1 list of ranges (intervals) : DATE
# ----------------------------------------------------------------------


## target language list ---------------------------- 1
LANG = (
	"en",
	"de",
	"fr",
	# "autres"
	"(NOT en) AND (NOT de) AND (NOT fr)"
	)



## target genre list -------------------------------- 2
GENRE = (
	"article-commentary",        # ARTICLE
	"brief-report",              # ARTICLE
	"case-report",               # ARTICLE
	"meeting-report",            # ARTICLE
	"rapid-communication",       # ARTICLE
	"research-article",          # ARTICLE
	"review-article",            # ARTICLE
	
	# "abstract",          # AUTRES
	# "book-review",       # AUTRES
	# "letter",            # AUTRES
	
	# "e-book",            # EBOOK
	)

### or simply major doctype groups
# GENRE = ("ARTICLE","EBOOK","AUTRES")



# DATE --------------------------------------------- 3
# for dates there's no categories but bins
# use case: range => bins => quotas
DATE = (
	("*", 1959),
	(1960, 1979),
	(1980, 1989),
	(1990, 1999),
	(2000, "*")
	)



# SCICAT (aka academic discipline) ----------------- 4
SCAT = (
	# "WOS subject cats" scheme
	"ACOUSTICS",
	"AGRICULTURAL ECONOMICS & POLICY",
	"AGRICULTURAL ENGINEERING",
	"AGRICULTURE",
	"AGRICULTURE, DAIRY & ANIMAL SCIENCE",
	"AGRICULTURE, MULTIDISCIPLINARY",
	"AGRICULTURE, SOIL SCIENCE",
	"AGRONOMY",
	"ALLERGY",
	"ANESTHESIOLOGY",
	"ANTHROPOLOGY",
	"APPLIED LINGUISTICS",
	"AREA STUDIES",
	"ART",
	"ASTRONOMY & ASTROPHYSICS",
	"AUDIOLOGY & SPEECH-LANGUAGE PATHOLOGY",
	"AUTOMATION & CONTROL SYSTEMS",
	"BEHAVIORAL SCIENCES",
	"BIOCHEMICAL RESEARCH METHODS",
	"BIOCHEMISTRY & MOLECULAR BIOLOGY",
	"BIODIVERSITY CONSERVATION",
	"BIOLOGY",
	"BIOPHYSICS",
	"BIOTECHNOLOGY & APPLIED MICROBIOLOGY",
	"BUSINESS",
	"BUSINESS, FINANCE",
	"CARDIAC & CARDIOVASCULAR SYSTEMS",
	"CELL & TISSUE ENGINEERING",
	"CELL BIOLOGY",
	"CHEMISTRY",
	"CHEMISTRY, ANALYTICAL",
	"CHEMISTRY, APPLIED",
	"CHEMISTRY, INORGANIC & NUCLEAR",
	"CHEMISTRY, MEDICINAL",
	"CHEMISTRY, MULTIDISCIPLINARY",
	"CHEMISTRY, ORGANIC",
	"CHEMISTRY, PHYSICAL",
	"CLINICAL NEUROLOGY",
	"COMMUNICATION",
	"COMPUTER SCIENCE, ARTIFICIAL INTELLIGENCE",
	"COMPUTER SCIENCE, CYBERNETICS",
	"COMPUTER SCIENCE, HARDWARE & ARCHITECTURE",
	"COMPUTER SCIENCE, INFORMATION SYSTEMS",
	"COMPUTER SCIENCE, INTERDISCIPLINARY APPLICATIONS",
	"COMPUTER SCIENCE, SOFTWARE ENGINEERING",
	"COMPUTER SCIENCE, THEORY & METHODS",
	"CONSTRUCTION & BUILDING TECHNOLOGY",
	"CRIMINOLOGY & PENOLOGY",
	"CRITICAL CARE MEDICINE",
	"CRYSTALLOGRAPHY",
	"CULTURAL STUDIES",
	"DEMOGRAPHY",
	"DENTISTRY, ORAL SURGERY & MEDICINE",
	"DERMATOLOGY",
	"DEVELOPMENTAL BIOLOGY",
	"ECOLOGY",
	"ECONOMICS",
	"EDUCATION & EDUCATIONAL RESEARCH",
	"EDUCATION, SCIENTIFIC DISCIPLINES",
	"EDUCATION, SPECIAL",
	"ELECTROCHEMISTRY",
	"EMERGENCY MEDICINE",
	"ENDOCRINOLOGY & METABOLISM",
	"ENERGY & FUELS",
	"ENGINEERING",
	"ENGINEERING, AEROSPACE",
	"ENGINEERING, BIOMEDICAL",
	"ENGINEERING, CHEMICAL",
	"ENGINEERING, CIVIL",
	"ENGINEERING, ELECTRICAL & ELECTRONIC",
	"ENGINEERING, ENVIRONMENTAL",
	"ENGINEERING, GEOLOGICAL",
	"ENGINEERING, INDUSTRIAL",
	"ENGINEERING, MANUFACTURING",
	"ENGINEERING, MARINE",
	"ENGINEERING, MECHANICAL",
	"ENGINEERING, MULTIDISCIPLINARY",
	"ENGINEERING, OCEAN",
	"ENGINEERING, PETROLEUM",
	"ENTOMOLOGY",
	"ENVIRONMENTAL SCIENCES",
	"ENVIRONMENTAL STUDIES",
	"ERGONOMICS",
	"ETHICS",
	"ETHNIC STUDIES",
	"EVOLUTIONARY BIOLOGY",
	"FAMILY STUDIES",
	"FILM, RADIO, TELEVISION",
	"FISHERIES",
	"FOOD SCIENCE & TECHNOLOGY",
	"FORESTRY",
	"GASTROENTEROLOGY & HEPATOLOGY",
	"GENETICS & HEREDITY",
	"GEOCHEMISTRY & GEOPHYSICS",
	"GEOGRAPHY",
	"GEOGRAPHY, PHYSICAL",
	"GEOLOGY",
	"GEOSCIENCES, MULTIDISCIPLINARY",
	"GERIATRICS & GERONTOLOGY",
	"GERONTOLOGY",
	"HEALTH CARE SCIENCES & SERVICES",
	"HEALTH POLICY & SERVICES",
	"HEMATOLOGY",
	"HISTORY",
	"HISTORY & PHILOSOPHY OF SCIENCE",
	"HISTORY OF SOCIAL SCIENCES",
	"HORTICULTURE",
	"HOSPITALITY, LEISURE, SPORT & TOURISM",
	"HUMANITIES, MULTIDISCIPLINARY",
	"IMAGING SCIENCE & PHOTOGRAPHIC TECHNOLOGY",
	"IMMUNOLOGY",
	"INFECTIOUS DISEASES",
	"INFORMATION SCIENCE & LIBRARY SCIENCE",
	"INSTRUMENTS & INSTRUMENTATION",
	"INTEGRATIVE & COMPLEMENTARY MEDICINE",
	"INTERNATIONAL RELATIONS",
	"LANGUAGE & LINGUISTICS",
	"LAW",
	"LINGUISTICS",
	"LITERARY THEORY & CRITICISM",
	"LITERATURE",
	"LITERATURE, AMERICAN",
	"LITERATURE, ROMANCE",
	"LOGIC",
	"MANAGEMENT",
	"MARINE & FRESHWATER BIOLOGY",
	"MATERIALS SCIENCE",
	"MATERIALS SCIENCE, BIOMATERIALS",
	"MATERIALS SCIENCE, CERAMICS",
	"MATERIALS SCIENCE, CHARACTERIZATION & TESTING",
	"MATERIALS SCIENCE, COATINGS & FILMS",
	"MATERIALS SCIENCE, COMPOSITES",
	"MATERIALS SCIENCE, MULTIDISCIPLINARY",
	"MATERIALS SCIENCE, TEXTILES",
	"MATHEMATICAL & COMPUTATIONAL BIOLOGY",
	"MATHEMATICS",
	"MATHEMATICS, APPLIED",
	"MATHEMATICS, INTERDISCIPLINARY APPLICATIONS",
	"MECHANICS",
	"MEDICAL ETHICS",
	"MEDICAL INFORMATICS",
	"MEDICAL LABORATORY TECHNOLOGY",
	"MEDICINE, GENERAL & INTERNAL",
	"MEDICINE, LEGAL",
	"MEDICINE, RESEARCH & EXPERIMENTAL",
	"METALLURGY",
	"METALLURGY & METALLURGICAL ENGINEERING",
	"METEOROLOGY & ATMOSPHERIC SCIENCES",
	"MICROBIOLOGY",
	"MICROSCOPY",
	"MINERALOGY",
	"MINING & MINERAL PROCESSING",
	"MULTIDISCIPLINARY SCIENCES",
	"MUSIC",
	"MYCOLOGY",
	"NANOSCIENCE & NANOTECHNOLOGY",
	"NEUROIMAGING",
	"NEUROSCIENCES",
	"NUCLEAR SCIENCE & TECHNOLOGY",
	"NURSING",
	"NUTRITION & DIETETICS",
	"OBSTETRICS & GYNECOLOGY",
	"OCEANOGRAPHY",
	"ONCOLOGY",
	"OPERATIONS RESEARCH & MANAGEMENT SCIENCE",
	"OPHTHALMOLOGY",
	"OPTICS",
	"ORTHOPEDICS",
	"OTORHINOLARYNGOLOGY",
	"PALEONTOLOGY",
	"PARASITOLOGY",
	"PATHOLOGY",
	"PEDIATRICS",
	"PERIPHERAL VASCULAR DISEASE",
	"PHARMACOLOGY & PHARMACY",
	"PHILOSOPHY",
	"PHYSICS",
	"PHYSICS, APPLIED",
	"PHYSICS, ATOMIC, MOLECULAR & CHEMICAL",
	"PHYSICS, CONDENSED MATTER",
	"PHYSICS, FLUIDS & PLASMAS",
	"PHYSICS, MATHEMATICAL",
	"PHYSICS, MULTIDISCIPLINARY",
	"PHYSICS, NUCLEAR",
	"PHYSICS, PARTICLES & FIELDS",
	"PHYSIOLOGY",
	"PLANNING & DEVELOPMENT",
	"PLANT SCIENCES",
	"POLITICAL SCIENCE",
	"POLYMER SCIENCE",
	"PRIMARY HEALTH CARE",
	"PSYCHIATRY",
	"PSYCHOLOGY",
	"PSYCHOLOGY, APPLIED",
	"PSYCHOLOGY, BIOLOGICAL",
	"PSYCHOLOGY, CLINICAL",
	"PSYCHOLOGY, DEVELOPMENTAL",
	"PSYCHOLOGY, EDUCATIONAL",
	"PSYCHOLOGY, EXPERIMENTAL",
	"PSYCHOLOGY, MULTIDISCIPLINARY",
	"PSYCHOLOGY, SOCIAL",
	"PUBLIC ADMINISTRATION",
	"PUBLIC, ENVIRONMENTAL & OCCUPATIONAL HEALTH",
	"RADIOLOGY, NUCLEAR MEDICINE & MEDICAL IMAGING",
	"REHABILITATION",
	"RELIGION",
	"REMOTE SENSING",
	"REPRODUCTIVE BIOLOGY",
	"RESPIRATORY SYSTEM",
	"RHEUMATOLOGY",
	"ROBOTICS",
	"SOCIAL ISSUES",
	"SOCIAL SCIENCES, BIOMEDICAL",
	"SOCIAL SCIENCES, INTERDISCIPLINARY",
	"SOCIAL SCIENCES, MATHEMATICAL METHODS",
	"SOCIAL WORK",
	"SOCIOLOGY",
	"SOIL SCIENCE",
	"SPECTROSCOPY",
	"SPORT SCIENCES",
	"STATISTICS & PROBABILITY",
	"SUBSTANCE ABUSE",
	"SURGERY",
	"TELECOMMUNICATIONS",
	"THERMODYNAMICS",
	"TOXICOLOGY",
	"TRANSPLANTATION",
	"TRANSPORTATION",
	"TRANSPORTATION SCIENCE & TECHNOLOGY",
	"TROPICAL MEDICINE",
	"URBAN STUDIES",
	"UROLOGY & NEPHROLOGY",
	"VETERINARY SCIENCES",
	"VIROLOGY",
	"WATER RESOURCES",
	"WOMEN'S STUDIES",
	"ZOOLOGY"
)