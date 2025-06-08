"""
A script that prints results of a potential migration where everyone's 1v1 rank to keep the same curve, but ensure a 1000 average ELO economy.
Also set's the sigma value to 0, since we don't use it in a raw ELO system.
"""
import json

import yaml
from pathlib import Path

# Define the relative path to the directory
yaml_dir = Path("../astron/databases/astrondb")
key_to_check = "setSkillProfiles"

old_mu_economy = 0
new_mu_economy = 0

old_sr_economy = 0
new_sr_economy = 0

profiles_viewed = 0
profiles_changed = 0

# Loop through all .yaml and .yml files in the directory
for yaml_file in yaml_dir.glob("*.yaml"):

    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        continue

    if 'fields' not in data:
        continue

    if key_to_check not in data['fields']:
        continue

    # Get the name, cut off the quotes and the tuple parentheses.
    name = data['fields']['setName'][2:-2]

    # Get the profile data, cut off the tuple parentheses.
    profiles = data['fields'][key_to_check][1:-1]
    # Replace all the curly braces with [], so we can listify this in JSON.
    profiles = profiles.replace('{', '[').replace('}', ']')
    # Use JSON to convert it to a readable python obj.
    parsed = json.loads(profiles)

    # Perform modifications.
    for profile in list(parsed):
        _id, key, mu, _, sr, won, played, placements = profile
        # If this isn't the mode we care about, skip.
        if key != '1v1_crane':
            continue

        old_mu_economy += mu
        old_sr_economy += sr
        profiles_viewed += 1

        above_1k = mu - 1000
        if above_1k <= 0:
            new_mu_economy += mu
            new_sr_economy += sr
            print(f"Skipping {name}, under 1k")
            continue

        profiles_changed += 1

        sigma = 0
        old_mu = mu
        old_sr = sr
        mu = (mu-1000)**(7/9) + 1000
        mu = int(mu.real)
        sr = (sr-1000)**(7/9) + 1000
        sr = int(sr.real)

        new_mu_economy += mu
        new_sr_economy += sr

        print(f"{name}: {old_mu} | {old_sr} -> {mu} | {sr}")

print()
print(f"profiles changed/viewed: {profiles_changed}/{profiles_viewed}")
print(f"mu economy: {old_mu_economy} -> {new_mu_economy}")
print(f"sr economy: {old_sr_economy} -> {new_sr_economy}")
print()
print(f"old -> new avg mu: {old_mu_economy / profiles_viewed:.0f} -> {new_mu_economy / profiles_viewed:.0f}")
print(f"old -> new avg sr: {old_sr_economy / profiles_viewed:.0f} -> {new_sr_economy / profiles_viewed:.0f}")