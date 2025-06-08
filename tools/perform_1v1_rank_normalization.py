"""
A script that modifies everyone's 1v1 rank to keep the same curve, but ensure a 1000 average ELO economy.
Also set's the sigma value to 0, since we don't use it in a raw ELO system.
"""

prompt = input("What you are about to do is going to alter the YAML database by normalizing everyone's 1v1 rank profile."
               " Are you sure you want to do this? If so, type CONFIRM and hit enter.")

if prompt != "CONFIRM":
    print("Cancelling script!")
    exit(1)

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

    modifications_made = False

    # Perform modifications.
    for i, profile in enumerate(list(parsed)):
        _id, key, mu, sigma, sr, won, played, placements = profile
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

        modifications_made = True

        profiles_changed += 1

        sigma = 0
        old_mu = mu
        old_sr = sr
        mu = (mu-1000)**(7/9) + 1000
        mu = int(mu.real)
        sr = (sr-1000)**(7/9) + 1000
        sr = int(sr.real)

        # Replace the data.
        parsed[i] = [_id, key, mu, sigma, sr, won, played, placements]

        new_mu_economy += mu
        new_sr_economy += sr

        print(f"{name}: {old_mu} | {old_sr} -> {mu} | {sr}")

    # Save the data back to this user.
    if not modifications_made:
        continue

    # This is kinda aids, but YAML files for some reason store complex data as strings.
    # We need to serialize the data we overwrote into the format the YAML expects.
    string_objects_to_dump: list[str] = []  # String representation of the objects to dump

    # Loop through all the JSON objects.
    for json_object in parsed:
        sb = ''
        for val in json_object:
            # Fun stuff, if this is a string, we need to surround it in quotations.
            surrounding_char = '"' if isinstance(val, str) else ''
            sb += surrounding_char + str(val) + surrounding_char + ', '
        # Append the string version of the JSON object. It is just the values of the list comma separated, contained in a curly brace.
        sb = sb[:-2]
        string_objects_to_dump.append("{" + sb + "}")

    # Now, join the objects by a comma within a "list", and wrap this in parentheses.
    inner_entry = f"([{', '.join(string_objects_to_dump)}])"


    # Set the new string!
    data['fields'][key_to_check] = inner_entry

    # Reopen the file in write mode and write back the data.
    with open(yaml_file, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False)

print()
print(f"profiles changed/viewed: {profiles_changed}/{profiles_viewed}")
print(f"mu economy: {old_mu_economy} -> {new_mu_economy}")
print(f"sr economy: {old_sr_economy} -> {new_sr_economy}")
print()
print(f"old -> new avg mu: {old_mu_economy / profiles_viewed:.0f} -> {new_mu_economy / profiles_viewed:.0f}")
print(f"old -> new avg sr: {old_sr_economy / profiles_viewed:.0f} -> {new_sr_economy / profiles_viewed:.0f}")