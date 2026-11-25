# Agent d'analyse de données agricoles 🤖🌾

Un agent LLM qui répond à des questions en français sur des données de rendement agricole : il explore la table, écrit des requêtes SQL, les exécute, **corrige lui-même ses erreurs**, puis répond avec des chiffres.

> 🚧 Projet en cours. Il prolonge mon stage à l'INRAE sur la génération de requêtes HiveQL par LLM (publication ICSOC 2025) : ici, l'agent ne se contente pas de générer la requête, il l'exécute, vérifie le résultat et se corrige.

## Exemple

```
Question : Quel pays a le meilleur rendement moyen de blé (Wheat) ?
  [étape 1] l'agent appelle decrire_table {}
  [étape 2] l'agent appelle executer_sql {...}   → erreur de colonne
  [étape 3] l'agent appelle executer_sql {...}   → requête corrigée
Réponse : ...
```

## Étapes du projet

- [x] **1 – Agent à la main** : boucle d'agent sans framework, appel d'outils, auto-correction (`etape1_agent_a_la_main.py`)
- [ ] **2 – Outils supplémentaires** : graphiques
- [ ] **3 – Version LangGraph**
- [ ] **4 – Évaluation** : jeu de questions de référence et taux de réussite
- [ ] **5 – Interface** Streamlit ou Gradio

## Techniques

Tool calling · boucle ReAct · auto-correction · garde-fou SQL (lecture seule) · DuckDB

## Installation

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate    ·    Mac/Linux : source .venv/bin/activate
pip install -r requirements.txt
```

1. Télécharger `yield_df.csv` depuis le [Crop Yield Prediction Dataset](https://www.kaggle.com/datasets/patelris/crop-yield-prediction-dataset) (Kaggle) et le placer dans `data/`.
2. Copier `.env.example` en `.env` et choisir le LLM (Ollama en local, ou un fournisseur en ligne).
3. Lancer : `python etape1_agent_a_la_main.py`

---

Dahbia Moussi · [Portfolio](https://moussidahbia.github.io) · [LinkedIn](https://www.linkedin.com/in/dahbia-moussi-94b6b3297/)
