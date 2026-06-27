TUTO ICI : https://youtu.be/OZszrijbE14?si=SDZ6GeUprF50AUuE 
---------------------------------------------------------------------------------
# Discord Username Checker

Un outil rapide et simple pour vérifier la disponibilité de pseudos Discord spécifiques.
Idéal pour trouver des usernames rares, clean, OG ou personnalisés avant qu’ils soient pris.

---

## ✨ Fonctionnalités

* Vérification automatique de usernames Discord
* Support des listes de pseudos personnalisés
* Vérification rapide et optimisée
* Interface simple à utiliser
* Affichage clair des usernames disponibles / pris
* Notification automatique via webhook lorsqu’un pseudo est disponible
* Logs propres et lisibles
* Léger et rapide

---

## 📦 Installation

Clone le repository :

```bash
git clone https://github.com/367w/Discord-Username-Checker.git
cd Discord-Username-Checker
```

Installe les dépendances :

```bash
pip install -r requirements.txt
```

---

## 🚀 Utilisation

Ajoute tes pseudos dans :

```python
Checker.py
```

Exemple :

```python
usernames = [
    "shadow",
    "velocity",
    "night"
]
```

Ajoute également ton webhook Discord dans le fichier :

```python
WEBHOOK_URL = "TON_WEBHOOK"
```

Puis lance le tool :

```bash
python Checker.py
```

---

## 📷 Exemple

```bash
[AVAILABLE] shadow
[TAKEN] velocity
[TAKEN] night
```

### Exemple de notification webhook

```yaml
@everyone AS OF 05/27/2026 10:01:40 PM, YOUR USERNAME IS AVAILABLE!
```

---

## 🛠️ Technologies

* Python
* Requests
* Threading
* Colorama

---

## ⚠️ Disclaimer

Cet outil est destiné à un usage éducatif et personnel uniquement.
Respecte les Conditions d’Utilisation de Discord lors de son utilisation.

---

## ⭐ Support

Si le projet t’aide :

* Mets une étoile au repository
* Fork le projet
* Propose des améliorations

---

## 👤 Auteur

Développé par **Kaiz** 🚀

Discord : `q354`
