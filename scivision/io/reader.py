import os
from urllib.parse import urlparse

import fsspec
import intake
import yaml

from ..koala import koala
from .installer import install_package
from .wrapper import PretrainedModel


def _is_url(path: os.PathLike) -> bool:
    return urlparse(path).scheme in ("http", "https",)


def _parse_url(path: os.PathLike, branch: str = "main"):
    """Parse a URL and convert to a raw github url if necessary."""
    parsed = urlparse(path)
    if not parsed.netloc == "github.com":
        return parsed.geturl()

    # construct the new github path
    parsed = parsed._replace(netloc="raw.githubusercontent.com")
    split = list(filter(None, parsed.path.split("/")))
    new_path = "/".join(split[:2]) + f"/{branch}/" + "/".join(split[2:])
    parsed = parsed._replace(path=new_path)
    return parsed.geturl()


def _parse_config(path: os.PathLike, branch: str = "main") -> str:
    """Parse the scivision.yml file from a GitHub repository.
    Will also accept differently named yaml if a full path provided or a local file.
    """

    if _is_url(path):
        path = _parse_url(path, branch)

    # check that this is a path to a yaml file
    # if not, assume it is a repo containing "scivision.yml"
    if not path.endswith((".yml", ".yaml",)):
        path = path + "scivision.yml"
    return path


@koala
def load_pretrained_model(
    path: os.PathLike,
    branch: str = "main",
    allow_install: bool = False,
    model: str = "default",
    load_multiple: bool = False,
    *args,
    **kwargs,
) -> PretrainedModel:
    """Load a pre-trained model.

    Parameters
    ----------
    path : PathLike
        The filename, path or URL of a pretrained model description.
    branch : str, default = main
        Specify the name of a github branch if loading from github.
    allow_install : bool, default = False
        Allow installation of remote package via pip.
    model : str, default = default
        Specify the name of the model if there is > 1.
    load_multiple : bool, default = False
        Modifies the return to be a list of scivision.PretrainedModel's.

    Returns
    -------
    pretrained_model : scivision.PretrainedModel
        The instantiated pre-trained model.
    """

    path = _parse_config(path, branch)
    # fsspec will throw an error if the path does not exist
    file = fsspec.open(path)
    # parse the config file:
    with file as config_file:
        stream = config_file.read()
        config = yaml.load(stream) # yaml.safe_load doesn't like a list of models
    # Create a list that will contain one or multiple model configs
    config_list = []
    if "models" in config:
        if load_multiple:
            # Create a config for each model
            for model_dict in config["models"]:
                new_config = {}
                new_config["name"] = config["name"]
                new_config["url"] = config["url"]
                new_config["import"] = config["import"]
                new_config["model"] = model_dict["model"]
                new_config["args"] = model_dict["args"]
                new_config["prediction_fn"] = model_dict["prediction_fn"]
                config_list.append(new_config)
        else:
            # Choose the first model in the list by default
            if model == "default":
                config["model"] = config["models"][0]["model"]
                config["args"] = config["models"][0]["args"]
                config["prediction_fn"] = config["models"][0]["prediction_fn"]
            # Choose the named model:
            else:
                for model_dict in config["models"]:
                    if model_dict["model"] == model:
                        config["model"] = model_dict["model"]
                        config["args"] = model_dict["args"]
                        config["prediction_fn"] = model_dict["prediction_fn"]
                        break
                # Check that a model of name "model" in scivision.yml config
                if "model" not in config:
                    raise ValueError("model name does not exist")
            config_list.append(config)
    else:
        # Check that a model of name "model" in scivision.yml config
        if model != "default":
            raise ValueError("model name does not exist")
        config_list.append(config)
    loaded_models = []
    for config in config_list:
        # make sure a model at least has an input to the function
        assert "X" in config["prediction_fn"]["args"].keys()

        # try to install the package if necessary
        install_package(config, allow_install=allow_install)

        loaded_models.append(PretrainedModel(config))
    if len(loaded_models) == 1:
        return loaded_models[0]
    return loaded_models


def load_dataset(
    path: os.PathLike,
    branch: str = "main"
) -> intake.catalog.local.YAMLFileCatalog:
    """Load a dataset.

    Parameters
    ----------
    path : PathLike
        The filename, path or URL of an intake catalog, which links to a dataset.
    branch : str, default = main
        Specify the name of a github branch if loading from github.

    Returns
    -------
    intake.catalog.local.YAMLFileCatalog
        The intake catalog object from which an xarray dataset can be created.
    """

    path = _parse_config(path, branch)
    # fsspec will throw an error if the path does not exist
    fsspec.open(path)
    return intake.open_catalog(path)
