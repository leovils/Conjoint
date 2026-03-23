import random
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

class ConjointEngine:
    def __init__(self, attributes, forbidden_pairs_str):
        self.attributes = attributes
        self.forbidden = self._parse_forbidden(forbidden_pairs_str)
        self.history = []
        
        # Build one-hot mapping. We will use dummy encoding.
        # To avoid dummy variable trap in traditional multinomial, we could drop one level.
        # However, for Ridge Logistic Regression (L2 penalty) dropping is not strictly required.
        # We will create a list of all features.
        self.features = []
        for attr, levels in attributes.items():
            for lvl in levels:
                self.features.append(f"{attr}::{lvl}")
                
        self.betas = np.zeros(len(self.features)) # Inicializamos com zeros
        self.convergence_threshold = 0.05
        self.min_pairs = 10
        self.max_pairs = 18

    def _parse_forbidden(self, forbidden_list):
        parsed = []
        for rule in forbidden_list:
            parts = rule.split(' + ')
            if len(parts) == 2:
                # "Atributo: Nivel"
                attrA = parts[0].split(': ')[0]
                lvlA = parts[0].split(': ')[1]
                attrB = parts[1].split(': ')[0]
                lvlB = parts[1].split(': ')[1]
                parsed.append({attrA: lvlA, attrB: lvlB})
        return parsed

    def _is_forbidden(self, profile):
        for rule in self.forbidden:
            match = True
            for rule_attr, rule_lvl in rule.items():
                if profile.get(rule_attr) != rule_lvl:
                    match = False
                    break
            if match:
                return True
        return False

    def _generate_random_profile(self):
        profile = {}
        for attr, levels in self.attributes.items():
            profile[attr] = random.choice(levels)
        return profile

    def generate_pair(self):
        # Gera dois perfis diferentes que não violem regras
        max_attempts = 100
        for _ in range(max_attempts):
            pA = self._generate_random_profile()
            if self._is_forbidden(pA): continue
            
            pB = self._generate_random_profile()
            if self._is_forbidden(pB): continue
            
            if pA != pB:
                return {'A': pA, 'B': pB}
        
        # Falha de segurança se as regras forem muito restritas
        return {'A': pA, 'B': pB}

    def _encode_profile(self, profile):
        vec = np.zeros(len(self.features))
        for attr, lvl in profile.items():
            feat_name = f"{attr}::{lvl}"
            if feat_name in self.features:
                idx = self.features.index(feat_name)
                vec[idx] = 1.0
        return vec

    def register_choice(self, pair, chosen_option):
        # A escolha (A ou B)
        # Se escolheu A, y=1 para A-B
        # Se escolheu B, y=0 para A-B
        
        pA = self._encode_profile(pair['A'])
        pB = self._encode_profile(pair['B'])
        
        diff_vector = pA - pB
        y = 1 if chosen_option == 'A' else 0
        
        self.history.append({
            'raw_A': pair['A'],
            'raw_B': pair['B'],
            'diff_vector': diff_vector,
            'choice_A': y,
        })
        
        return self._check_stopping_criteria()

    def _calculate_betas(self):
        if len(self.history) < 2:
            return self.betas
            
        X = np.array([h['diff_vector'] for h in self.history])
        y = np.array([h['choice_A'] for h in self.history])
        
        # Logistic Regression sem intercepto (já que diff de 0 deve ter prob de 50%)
        # Regularização L2 para evitar Betas explodindo (Ridge logic)
        clf = LogisticRegression(fit_intercept=False, penalty='l2', C=1.0, solver='lbfgs')
        
        try:
            # Se todas categorias de Y forem iguais, a regressão falha
            if len(np.unique(y)) > 1:
                clf.fit(X, y)
                return clf.coef_[0]
            else:
                return self.betas
        except Exception as e:
            return self.betas

    def _check_stopping_criteria(self):
        n = len(self.history)
        
        old_betas = self.betas.copy()
        self.betas = self._calculate_betas()
        
        if n >= self.max_pairs:
            return True
            
        if n >= self.min_pairs:
            # Calcular a variação máxima absoluta e relativa
            # Para evitar divisao por zero, usamos uma constante no denominador
            # abs(new - old) / (abs(old) + 1e-5)
            # Ou apenas a mudança percentual média da utilidade
            diff = np.abs(self.betas - old_betas)
            rel_diff = diff / (np.abs(old_betas) + 1e-5)
            max_variation = np.max(rel_diff)
            
            if max_variation < self.convergence_threshold:
                return True
                
        return False

    def get_history_df(self):
        rows = []
        for idx, h in enumerate(self.history):
            row = {'Round': idx + 1, 'Choice': 'A' if h['choice_A'] == 1 else 'B'}
            for attr in self.attributes.keys():
                row[f"OpA_{attr}"] = h['raw_A'][attr]
                row[f"OpB_{attr}"] = h['raw_B'][attr]
            rows.append(row)
        return pd.DataFrame(rows)

    def get_utilities_df(self):
        return pd.DataFrame({
            "Nível (Feature)": self.features,
            "Utilidade (Beta)": self.betas
        })
        
    def get_importance_df(self):
        # Range of utilities within each attribute
        importance = {}
        for attr in self.attributes.keys():
            # Get betas for this attribute
            indices = [i for i, f in enumerate(self.features) if f.startswith(attr + "::")]
            b = self.betas[indices]
            range_b = np.max(b) - np.min(b)
            importance[attr] = range_b
            
        total = sum(importance.values()) + 1e-9
        
        rows = []
        for attr, imp in importance.items():
            rows.append({
                "Atributo": attr,
                "Relative Importance (%)": round((imp / total) * 100, 2)
            })
            
        return pd.DataFrame(rows)

    def simulate_market_share(self, profile1, profile2):
        v1 = self._encode_profile(profile1)
        v2 = self._encode_profile(profile2)
        
        # U_1 = Sum(Beta * V1)
        u1 = np.dot(v1, self.betas)
        u2 = np.dot(v2, self.betas)
        
        # Multinomial Logit Formula
        exp_u1 = np.exp(u1)
        exp_u2 = np.exp(u2)
        total_exp = exp_u1 + exp_u2
        
        return exp_u1 / total_exp, exp_u2 / total_exp
