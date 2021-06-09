import argparse
import pathlib
import warnings

from ..rtdc_dataset import fmt_tdms, new_dataset, write_hdf5

from . import common


def tdms2rtdc(path_tdms=None, path_rtdc=None, compute_features=False,
              skip_initial_empty_image=True, skip_final_empty_image=True,
              verbose=False):
    """Convert .tdms datasets to the hdf5-based .rtdc file format

    Parameters
    ----------
    path_tdms: str or pathlib.Path
        Path to input .tdms file
    path_rtdc: str or pathlib.Path
        Path to output .rtdc file
    compute_features: bool
        If `True`, compute all ancillary features and store them in the
        output file
    skip_initial_empty_image: bool
        In old versions of Shape-In, the first image was sometimes
        not stored in the resulting .avi file. In dclab, such images
        are represented as zero-valued images. If `True` (default),
        this first image is not included in the resulting .rtdc file.
    skip_final_empty_image: bool
        In other versions of Shape-In, the final image is sometimes
        also not stored in the .avi file. If `True` (default), this
        final image is not included in the resulting .rtdc file.
    verbose: bool
        If `True`, print messages to stdout
    """
    if path_tdms is None or path_rtdc is None:
        parser = tdms2rtdc_parser()
        args = parser.parse_args()

        path_tdms = pathlib.Path(args.tdms_path).resolve()
        path_rtdc = pathlib.Path(args.rtdc_path)
        compute_features = args.compute_features
        skip_initial_empty_image = not args.include_empty_boundary_images
        skip_final_empty_image = not args.include_empty_boundary_images
        verbose = True

    if not path_tdms.suffix == ".tdms":
        raise ValueError("Please specify a .tdms file!")

    if not path_rtdc.suffix == ".rtdc":
        path_rtdc = path_rtdc.with_name(path_rtdc.name + ".rtdc")

    # Determine whether input path is a tdms file or a directory
    if path_tdms.is_dir():
        files_tdms = fmt_tdms.get_tdms_files(path_tdms)
        if path_rtdc.is_file():
            raise ValueError("rtdc_path is a file: {}".format(path_rtdc))
        files_rtdc = []
        for ff in files_tdms:
            ff = pathlib.Path(ff)
            rp = ff.relative_to(path_tdms)
            # determine output file name (same relative path)
            rpr = path_rtdc / rp.with_suffix(".rtdc")
            files_rtdc.append(rpr)
    else:
        files_tdms = [path_tdms]
        files_rtdc = [path_rtdc]

    for ii in range(len(files_tdms)):
        ff = pathlib.Path(files_tdms[ii])
        fr = pathlib.Path(files_rtdc[ii])

        if verbose:
            common.print_info(f"Converting {ii+1:d}/{len(files_tdms):d}: {ff}")
        # create directory
        if not fr.parent.exists():
            fr.parent.mkdir(parents=True)
        # load and export dataset
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # ignore ResourceWarning: unclosed file <_io.BufferedReader...>
            warnings.simplefilter("ignore", ResourceWarning)  # noqa: F821
            # ignore SlowVideoWarning
            warnings.simplefilter("ignore",
                                  fmt_tdms.event_image.SlowVideoWarning)
            if skip_initial_empty_image:
                # If the initial frame is skipped when empty,
                # suppress any related warning messages.
                warnings.simplefilter(
                    "ignore",
                    fmt_tdms.event_image.InitialFrameMissingWarning)

            with new_dataset(ff) as ds:
                # determine features to export
                if compute_features:
                    features = ds.features
                else:
                    # consider special case for "image", "trace", and "contour"
                    # (This will export both "mask" and "contour".
                    # The "mask" is computed from "contour" and it is needed
                    # by dclab for other ancillary features. We still keep
                    # "contour" because it is original data.
                    features = ds.features_innate

                common.skip_empty_image_events(
                    ds=ds,
                    initial=skip_initial_empty_image,
                    final=skip_final_empty_image)
                # export as hdf5
                ds.export.hdf5(path=fr,
                               features=features,
                               filtered=True,
                               override=True,
                               compression="gzip")

                # write logs
                custom_dict = {}
                # computed features
                cfeats = list(set(features) - set(ds.features_innate))
                if "mask" in features:
                    # Mask is always computed from contour data
                    cfeats.append("mask")
                custom_dict["ancillary features"] = sorted(cfeats)

                # command log
                logs = {"dclab-tdms2rtdc": common.get_command_log(
                    paths=[ff], custom_dict=custom_dict)}
                # warnings log
                if w:
                    logs["dclab-tdms2rtdc-warnings"] = \
                        common.assemble_warnings(w)
                logs.update(ds.logs)
                with write_hdf5.write(fr, logs=logs, mode="append",
                                      compression="gzip"):
                    pass


def tdms2rtdc_parser():
    descr = "Convert RT-DC .tdms files to the hdf5-based .rtdc file format. " \
            + "Note: Do not delete original .tdms files after conversion. " \
            + "The conversion might be incomplete."
    parser = argparse.ArgumentParser(description=descr)
    parser.add_argument('--compute-ancillary-features',
                        dest='compute_features',
                        action='store_true',
                        help='Compute features, such as volume or emodulus, '
                             + 'that are otherwise computed on-the-fly. '
                             + 'Use this if you want to minimize analysis '
                             + 'time in e.g. Shape-Out. CAUTION: ancillary '
                             + 'feature recipes might be subject to change '
                             + '(e.g. if an error is found in the recipe). '
                             + 'Disabling this option maximizes '
                             + 'compatibility with future versions and '
                             + 'allows to isolate the original data.')
    parser.set_defaults(compute_features=False)
    parser.add_argument('--include-empty-boundary-images',
                        dest='include_empty_boundary_images',
                        action='store_true',
                        help='In old versions of Shape-In, the first or last '
                             + 'images were sometimes not stored in the '
                             + 'resulting .avi file. In dclab, such images '
                             + 'are represented as zero-valued images. Set '
                             + 'this option, if you wish to include these '
                             + 'events with empty image data.')
    parser.set_defaults(include_empty_boundary_images=False)
    parser.add_argument('tdms_path', metavar="TDMS_PATH", type=str,
                        help='Input path (tdms file or folder containing '
                             + 'tdms files)')
    parser.add_argument('rtdc_path', metavar="RTDC_PATH", type=str,
                        help='Output path (file or folder), existing data '
                             + 'will be overridden')
    return parser
