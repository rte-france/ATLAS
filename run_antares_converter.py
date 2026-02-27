from atlas.modules.antares_to_atlas.antares_to_atlas import AntaresToAtlas

if __name__ == "__main__":
    converter = AntaresToAtlas.from_file("parameters_antares.yaml")
    dataset = converter.convert(study_path="data/antares")
