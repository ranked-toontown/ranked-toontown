import yaml
from pathlib import Path

# Define the relative path to the directory
yaml_dir = Path("../astron/databases/astrondb")
key_to_remove = "setSkillProfiles"

# Loop through all .yaml and .yml files in the directory
for yaml_file in yaml_dir.glob("*.yaml"):
    print(f"Processing {yaml_file}")
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f) or {}

    # If it's a dict and the key exists, remove it
    if isinstance(data, dict) and 'fields' in data:
        fields = data['fields']
        if isinstance(fields, dict) and key_to_remove in fields:
            print(f"Removing key '{key_to_remove}' from {yaml_file}. Value was: {fields[key_to_remove]}")
            del fields[key_to_remove]

            # Save the file back
            with open(yaml_file, 'w') as f:
                yaml.safe_dump(data, f, sort_keys=False)
