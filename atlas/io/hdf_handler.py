import os

import h5py
import numpy as np
import polars as pl


def explore_hdf5(hdf_file, output_dir):
    """
    Recursively explore HDF5 file and recreate structure while converting datasets to CSV

    Args:
        hdf_file: The HDF5 file object or group to explore
        output_dir: The directory where to save the folder structure and CSV files

    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Explore all items in the current group
    for key in hdf_file.keys():
        item = hdf_file[key]
        path = os.path.join(output_dir, key)

        # If item is a group (folder), recursively explore it
        if isinstance(item, h5py.Group):
            explore_hdf5(item, path)

        # If item is a dataset, convert to Polars dataframe and save as CSV
        elif isinstance(item, h5py.Dataset):
            try:
                # Read the dataset into a numpy array
                data = item[()]

                # Handle different dataset types
                if len(item.shape) == 1:
                    # 1D array - single column
                    df = pl.DataFrame({key: data})
                elif len(item.shape) == 2:
                    # 2D array - potentially a table with rows and columns
                    if item.dtype.kind in {"S", "O"}:
                        # String/object type - needs special handling
                        # Convert bytes to strings if necessary
                        if item.dtype.kind == "S":
                            data = np.array(
                                [
                                    s.decode("utf-8") if isinstance(s, bytes) else s
                                    for s in data.flatten()
                                ]
                            )
                            data = data.reshape(item.shape)

                        # Try to create a dataframe based on shape
                        if item.shape[1] == 1:
                            df = pl.DataFrame({key: data.flatten()})
                        else:
                            # Multiple columns - create column names
                            columns = {f"col_{i}": data[:, i] for i in range(item.shape[1])}
                            df = pl.DataFrame(columns)
                    # Numeric data
                    elif item.shape[1] == 1:
                        df = pl.DataFrame({key: data.flatten()})
                    else:
                        # Multiple columns - create column names
                        columns = {f"col_{i}": data[:, i] for i in range(item.shape[1])}
                        df = pl.DataFrame(columns)
                else:
                    # Higher dimensional data - flatten and save structure info
                    df = pl.DataFrame({"data": data.flatten(), "original_shape": str(item.shape)})

                # Save to CSV
                csv_path = f"{path}.csv"

                df.write_csv(csv_path)

            except Exception as e:
                print(f"Error processing dataset {key}: {e}")


def convert_hdf5_to_csv(hdf_path, output_dir):
    """
    Main function to convert HDF5 file to CSV files

    Args:
        hdf_path: Path to the HDF5 file
        output_dir: Output directory for the folder structure and CSV files

    """
    with h5py.File(hdf_path, "r") as hdf_file:
        hdf_file.visit(lambda name: print(f"- {name}"))

        explore_hdf5(hdf_file, output_dir)
