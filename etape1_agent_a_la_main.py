"""
Étape 1 – Un agent LLM « à la main », sans framework.

L'agent reçoit une question en français sur les données de rendement agricole.
À chaque tour de boucle, le LLM choisit soit d'appeler un outil (décrire la table,
exécuter une requête SQL), soit de donner sa réponse finale.
Si une requête échoue, l'erreur lui est renvoyée : il peut corriger et réessayer.
"""

import json
import os
from pathlib import Path

import duckdb                      # pyright: ignore[reportMissingImports] # moteur SQL qui lit directement les fichiers CSV
from dotenv import load_dotenv     # lit les réglages du fichier .env
from openai import OpenAI          # client compatible avec Ollama et la plupart des fournisseurs de LLM


# ---------------------------------------------------------------------------
# 1. Réglages
# ---------------------------------------------------------------------------

load_dotenv()  # charge les variables du fichier .env (adresse du LLM, clé, nom du modèle)

client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),  # par défaut : Ollama sur ton ordinateur
    api_key=os.getenv("LLM_API_KEY", "ollama"),  # Ollama n'a pas besoin de vraie clé
)
MODELE = os.getenv("LLM_MODEL", "qwen2.5:7b")

# Chemin du fichier de données, construit à partir de l'emplacement de ce script
CHEMIN_DONNEES = Path(__file__).parent / "data" / "yield_df.csv"
MAX_ETAPES = 6  # nombre maximum de tours de boucle, pour éviter que l'agent tourne indéfiniment


# ---------------------------------------------------------------------------
# 2. La base de données
# ---------------------------------------------------------------------------

connexion = duckdb.connect()  # une base DuckDB en mémoire
# On crée une « vue » nommée rendements : le CSV se comporte comme une table SQL
connexion.execute(
    f"CREATE VIEW rendements AS SELECT * FROM read_csv_auto('{CHEMIN_DONNEES.as_posix()}')"
)


# ---------------------------------------------------------------------------
# 3. Les outils : des fonctions Python normales que l'agent pourra appeler
# ---------------------------------------------------------------------------

def decrire_table() -> str:
    """Renvoie la liste des colonnes de la table rendements, avec leur type."""
    colonnes = connexion.execute("DESCRIBE rendements").fetchall()
    # Chaque ligne de DESCRIBE commence par (nom, type, ...) : on garde les deux premiers
    return "\n".join(f"{nom} ({type_sql})" for nom, type_sql, *_ in colonnes)


def executer_sql(requete: str) -> str:
    """Exécute une requête SELECT et renvoie au plus 20 lignes de résultat, sous forme de texte."""
    # Sécurité : on n'autorise que la lecture, jamais de modification des données
    if not requete.strip().lower().startswith("select"):
        return "Erreur : seules les requêtes SELECT sont autorisées."
    try:
        resultat = connexion.execute(requete).fetchdf()  # fetchdf() renvoie un tableau pandas
    except Exception as erreur:
        # On ne plante pas : on renvoie le message d'erreur à l'agent pour qu'il se corrige
        return f"Erreur SQL : {erreur}"
    if resultat.empty:
        return "La requête n'a renvoyé aucune ligne."
    return resultat.head(20).to_string(index=False)


# Dictionnaire qui relie le nom d'un outil (choisi par le LLM) à la vraie fonction Python
FONCTIONS = {
    "decrire_table": decrire_table,
    "executer_sql": executer_sql,
}

# Description des outils pour le LLM : c'est grâce à ces textes qu'il sait quand les utiliser
OUTILS = [
    {
        "type": "function",
        "function": {
            "name": "decrire_table",
            "description": "Donne les colonnes et les types de la table rendements. À appeler avant d'écrire une requête.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executer_sql",
            "description": "Exécute une requête SQL SELECT (syntaxe DuckDB) sur la table rendements et renvoie le résultat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requete": {"type": "string", "description": "La requête SQL SELECT à exécuter."}
                },
                "required": ["requete"],
            },
        },
    },
]

PROMPT_SYSTEME = """Tu es un assistant d'analyse de données agricoles.
Tu réponds aux questions en interrogeant la table SQL `rendements` avec tes outils.
Méthode :
1. Appelle d'abord decrire_table pour connaître les colonnes.
2. Écris une requête SQL avec executer_sql. Mets entre guillemets doubles les noms de colonnes
   qui contiennent des caractères spéciaux, par exemple "hg/ha_yield".
3. Si tu reçois une erreur, lis-la, corrige ta requête et réessaie.
4. Réponds en français, en une ou deux phrases, avec les chiffres trouvés.
Le rendement "hg/ha_yield" est en hectogrammes par hectare : divise par 10000 pour avoir des tonnes par hectare."""


# ---------------------------------------------------------------------------
# 4. La boucle de l'agent : le cœur du projet
# ---------------------------------------------------------------------------

def lancer_agent(question: str) -> str:
    """Fait tourner la boucle « le LLM réfléchit → appelle un outil → observe le résultat »."""
    # L'historique de la conversation : il grandit à chaque tour
    messages = [
        {"role": "system", "content": PROMPT_SYSTEME},
        {"role": "user", "content": question},
    ]

    for etape in range(1, MAX_ETAPES + 1):
        # 4a. On envoie tout l'historique au LLM, avec la liste des outils disponibles
        reponse = client.chat.completions.create(model=MODELE, messages=messages, tools=OUTILS)
        message = reponse.choices[0].message

        # 4b. Si le LLM ne demande aucun outil, c'est sa réponse finale
        if not message.tool_calls:
            return message.content

        # 4c. Sinon, on garde sa demande dans l'historique…
        messages.append(message.model_dump(exclude_none=True))

        # …puis on exécute chaque outil demandé
        for appel in message.tool_calls:
            nom_outil = appel.function.name
            try:
                arguments = json.loads(appel.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            print(f"  [étape {etape}] l'agent appelle {nom_outil} {arguments}")

            fonction = FONCTIONS.get(nom_outil)
            if fonction is None:
                resultat = f"Erreur : l'outil {nom_outil} n'existe pas."
            else:
                try:
                    resultat = fonction(**arguments)
                except TypeError as erreur:  # mauvais arguments fournis par le LLM
                    resultat = f"Erreur dans les arguments : {erreur}"

            # 4d. On renvoie le résultat au LLM, relié à sa demande par tool_call_id
            messages.append({"role": "tool", "tool_call_id": appel.id, "content": resultat})

    return "Je n'ai pas réussi à répondre en un nombre raisonnable d'étapes."


# ---------------------------------------------------------------------------
# 5. Lancement : ce bloc s'exécute quand on lance le fichier avec ▶
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    question = "Quil etait le rendement de l'Algerie en wheat en 1994?"
    print(f"Question : {question}\n")
    print(f"\nRéponse : {lancer_agent(question)}")
