import os
import sys
import shutil
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import leastsq
import pdfkit
import datetime

'''
Credit to https://people.duke.edu/~ccc14/pcfb/analysis.html for the code to fit 
the 4 parameter logistic regression for the standard curve
'''

def logistic4(x, A, B, C, D):
    """4PL logistic equation. Returns OD (y) based off standard concentration (x) """
    step1 = A-D
    step2 = x/C
    step3 = np.sign(step2) * (np.abs(step2)) ** B
    log_output = (step1/(1.0 + step3) + D)
    return log_output

def residuals(p, y, x):
    """Deviations of data from fitted 4PL curve"""
    A,B,C,D = p
    err = y-logistic4(x, A, B, C, D)
    return err

def peval(x, p):
    """Evaluated value at x with current parameters."""
    A,B,C,D = p
    return logistic4(x, A, B, C, D)

def get_conc(y, p):
    """returns concentraion (x) with OD (y) input"""
    A,B,C,D = p
    step1 = ((A-D)/(y-D)) - 1
    step2 = np.sign(step1) * (np.abs(step1)) ** (1/B)
    concentration = step2 * C
    return concentration

def mean_cv(group):
    """returns mean and cv of a group of wells"""
    group_ods = np.asarray(list(ods[group].values()))
    group_mean = sum(group_ods) / len(group_ods)
    group_sd = np.std(group_ods)
    group_cv = group_sd / group_mean
    return [group_mean, group_cv]

std_concs_dict = {"hero": [1000, 571.4285714, 326.5306122, 186.5889213, 106.6222407, 60.9269947,
                           34.81542555, 19.89452888, 11.36830222, 6.496172697, 3.712098684, 2.121199248],
                  "who-s": [922.74, 527.28, 301.3028571, 172.1730612, 98.38460641, 56.21977509,
                             32.12558577, 18.35747758, 10.48998719, 5.994278394, 3.425301939, 1.957315394],
                  "who-n": [976.32, 557.8971429, 318.7983673, 182.1704956, 104.0974261, 59.48424347, 33.99099627,
                           19.42342644, 11.09910082, 6.342343327, 3.624196187, 2.07096925]}



std_curve1_cells = ["B23", "C23", "D23", "E23", "F23", "G23", "H23", "I23", "J23", "K23", "L23", "M23"]
std_curve2_cells = ["B24", "C24", "D24", "E24", "F24", "G24", "H24", "I24", "J24", "K24", "L24", "M24"]

antigens = {"s" : "Spike", "n" : "Nucleocapsid", "n2": "Nucleocapsid2"}

cut_offs = {"s" : 0.175, "n" : 0.722, "n2": 0.1905}

if __name__ == "__main__":
    sys.path.insert(1, './scripts')
    from template import html
    from plate_plans import get_ods, get_samples
    plate_id = sys.argv[1]
    antigen = sys.argv[2]
    if antigen == "N-Spec":
        antigen = "n"
    if antigen == "N-Sens":
        antigen = "n2"
    include_pdf = sys.argv[3]
    std_concs = std_concs_dict[sys.argv[4]]
    conc_index = sys.argv[5]

    plateplan_file = plate_id + "-pplan.xlsx"
    platereader_file = plate_id + "-preader.xlsx"
    ignore_file = plate_id + "-ignore.csv"
    ods = get_ods(platereader_file) #retutns python dictionary with ods from plate
    sample_dilution = get_samples(plateplan_file) #returns python dictionary with samples names and dilutions

    print("Found plateplan file: %s" % plateplan_file)
    print("Found plate reader file: %s" % platereader_file)

    if ignore_file in os.listdir():
        print("Found ignore file: %s" % ignore_file)

    print("Antigen: %s" % antigens[antigen])

    np.set_printoptions(suppress=True) #suppresses scientific display of numbers

### remove bad wells using ignore file ###
    badwells = []
    badwells_group = []
    bad_std = []

    if ignore_file in os.listdir():
        with open(ignore_file) as infile:
            for line in infile:
                badwell = line.split(",")[0]
                group = line.split(",")[1].replace("\n", "")
                badwells.append(badwell)
                badwells_group.append(group)

    #if not in standard curve will delete. If in standard curve will take other standard OD. If both standard bad
    #add to list and delete below
    for group in list(ods.keys()):
        for well in list(ods[group].keys()):
            if well in badwells:
                if well not in std_curve1_cells and well not in std_curve2_cells:
                    del ods[group][well]
                else:
                    if well in std_curve1_cells:
                        alternate_well = well[0:2] + "4"
                        if alternate_well in std_curve2_cells:
                            bad_std.append(std_curve2_cells.index(alternate_well))
                            del ods[group][well]
                        else:
                            ods[group][well] = ods["std_curve2"][alternate_well]
                    if well in std_curve2_cells:
                        alternate_well = well[0:2] + "3"
                        if alternate_well in std_curve1_cells:
                            del ods[group][well]
                        else:
                            ods[group][well] = ods["std_curve1"][alternate_well]

    #delete bad std from from concentration list
    for std in bad_std:
        del std_concs[std]


##calculate CV for samples before blank subtracting
    sample_cv = {}
    for sample in ods.keys():
        if "sample" in sample:
            sample_ods = np.asarray(list(ods[sample].values()))
            mean = sum(sample_ods)/len(sample_ods)
            sd = np.std(sample_ods)
            cv = sd/mean
            sample_cv[sample] = round(cv, 2)


### subtract mean of blanks from all wells ###
    blk_mean = mean_cv("blk")[0]
    blk_cv = mean_cv("blk")[1]

    for group in ods.keys():
        for well in ods[group].keys():
            minblk_od = ods[group][well] - blk_mean
            ods[group][well] = minblk_od

### Fit standard curve using 4 parameter logistic regression ###
    print("Fitting standard curve")
    x = np.asarray(std_concs)

    std_curve1_ods = np.asarray(list(ods["std_curve1"].values()))
    std_curve2_ods = np.asarray(list(ods["std_curve2"].values()))

    y = (std_curve1_ods + std_curve2_ods) / 2.0

    # Initial guess for parameters
    p0 = [0, 1, 1, 1]

    # Fit equation using least squares optimization
    plsq = leastsq(residuals, p0, args=(y, x))

    # Plot results
    plt.plot(x, peval(x, plsq[0]))
    plt.plot(x, std_curve1_ods, '.', color='orange')
    plt.plot(x, std_curve2_ods, '.', color='orange')

    plt.xscale("log", basex=10)
    plt.title("Standard curve")
    plt.xlabel("Unit of standard")
    plt.ylabel("OD")

    fig_name = plate_id + ".png"
    fig_path = os.path.join("figs", fig_name)
    fig_path_html = os.path.join("html_reports/figs", fig_name)

    plt.savefig(fig_path)
    plt.savefig(fig_path_html)

### Calculate CV of each standard and check index QC
    std1_as_list = list(ods["std_curve1"].values())
    std2_as_list = list(ods["std_curve2"].values())

    std_cvs = {}
    for std in std1_as_list:
        list_pos = std1_as_list.index(std)
        st_mean = (std1_as_list[list_pos] + std2_as_list[list_pos]) / 2
        std_ods = np.asarray([std1_as_list[list_pos], std2_as_list[list_pos]])
        st_dev = np.std(std_ods)
        st_cv = st_dev / st_mean
        std_cvs["Std" + str(list_pos + 1)] = st_cv

    bad_stds = {}
    for std in std_cvs.keys():
        if std_cvs[std] >= 0.1:
            bad_stds[std] = round(std_cvs[std], 3)

    # check and if necessary exclude index standards
    index_stds = ["Std09", "Std10", "Std11"]
    failed_index_stds = []
    for index_std in index_stds:
        if index_std in bad_stds.keys():
            failed_index_stds.append(index_std)

    std_means = {"Std09": (std1_as_list[8] + std2_as_list[8]) / 2,
                 "Std10": (std1_as_list[9] + std2_as_list[9]) / 2,
                 "Std11": (std1_as_list[10] + std2_as_list[10]) / 2}

### calculate output variables###

    print("Calculating concentrations/index")
    sample_means = {}
    sample_concs = {}
    pos_neg = {}

    if conc_index == "conc":
        for sample in ods.keys():
            if "sample" in sample:
                sample_ods = np.asarray(list(ods[sample].values()))
                mean = sum(sample_ods)/len(sample_ods)
                sample_concs[sample] = round(get_conc(mean, plsq[0]), 6)
                sd = np.std(sample_ods)
                cv = sd/mean

                if mean < y[-1]:
                    sample_concs[sample] = "BelowCurve"
                elif mean > y[0]:
                    sample_concs[sample] = "AboveCurve"

                sample_means[sample] = round(mean, 3)

                if sample_means[sample].item() > cut_offs[antigen]:
                    pos_neg[sample] = "Pos"
                else:
                    pos_neg[sample] = "Neg"

    index_cutoffs = {"s" : {"Std09":0.643, "Std10":1.087, "Std11":1.707},
                     "n" : {"Std09":0.825, "Std10":1.287, "Std11":2.049},
                     "n2": {"Std09":0.340, "Std10":0.541, "Std11":0.873}
                     }

    if conc_index == "index":
        for sample in ods.keys():
            if "sample" in sample:
                sample_ods = np.asarray(list(ods[sample].values()))
                mean = sum(sample_ods)/len(sample_ods)
                sample_concs[sample] = round(get_conc(mean, plsq[0]), 6)
                sd = np.std(sample_ods)
                cv = sd/mean

                if mean < y[-1]:
                    sample_concs[sample] = "BelowCurve"
                elif mean > y[0]:
                    sample_concs[sample] = "AboveCurve"

                sample_means[sample] = round(mean, 3)

                sample_indices = {}
                index_posneg = {}

                for index_std in index_stds:
                    if index_std not in failed_index_stds:
                        sample_index = mean/std_means[index_std]
                        sample_indices[index_std] = sample_index
                        index_posneg[index_std] = sample_index > index_cutoffs[antigen][index_std]

                #call positive if >= 2 index above cut off
                pos_index_num = 0
                for i in index_posneg.values():
                    if i == True:
                        pos_index_num += 1

                if pos_index_num >=2:
                    pos_neg[sample] = "Pos"
                else:
                    pos_neg[sample] = "Neg"


### determine conditional output text ###

    if len(bad_stds) == 0:
        std_text = "all standards have a CV <0.1"
    else:
        std_text = "all standard CVs <0.1 except: %s" % str(bad_stds)

    ignore_wells = dict(zip(badwells, badwells_group))

    if len(badwells) == 0:
        ignore_text = "No wells exlcuded"
    else:
        ignore_text = "excluded these wells: %s" % ignore_wells

    if conc_index == "index":
        if len(failed_index_stds) >= 2:
            print("Index positive/negative call failed as 2 or more CVs >10%")
            quit()

### Output to pdf file ###
    print("Generating html file")
    now = datetime.datetime.now()
    date = "%s-%s-%s" % (now.day, now.strftime("%b"), now.year)

    html_page = html % (plate_id,
                            date,
                            antigens[antigen],
                            sys.argv[4],
                            sys.argv[5],
                            fig_path,
                            str(cut_offs[antigen]),
                            round(blk_mean, 3),
                            round(blk_cv, 3),

                            round(mean_cv("pos")[0], 3),
                            round(mean_cv("pos")[1], 3),

                            round(mean_cv("neg")[0], 3),
                            round(mean_cv("neg")[1], 3),

                            std_text,

                            ignore_text,

                            sample_dilution["sample01"].split("-")[0],
                                sample_means["sample01"],
                                sample_cv["sample01"],
                                sample_concs["sample01"],
                                pos_neg["sample01"],

                            sample_dilution["sample02"].split("-")[0],
                                sample_means["sample02"],
                                sample_cv["sample02"],
                                sample_concs["sample02"],
                                pos_neg["sample02"],

                            sample_dilution["sample03"].split("-")[0],
                                sample_means["sample03"],
                                sample_cv["sample03"],
                                sample_concs["sample03"],
                                pos_neg["sample03"],

                            sample_dilution["sample04"].split("-")[0],
                                sample_means["sample04"],
                                sample_cv["sample04"],
                                sample_concs["sample04"],
                                pos_neg["sample04"],

                            sample_dilution["sample05"].split("-")[0],
                                sample_means["sample05"],
                                sample_cv["sample05"],
                                sample_concs["sample05"],
                                pos_neg["sample05"],

                            sample_dilution["sample06"].split("-")[0],
                                sample_means["sample06"],
                                sample_cv["sample06"],
                                sample_concs["sample06"],
                                pos_neg["sample06"],

                            sample_dilution["sample07"].split("-")[0],
                                sample_means["sample07"],
                                sample_cv["sample07"],
                                sample_concs["sample07"],
                                pos_neg["sample07"],

                            sample_dilution["sample08"].split("-")[0],
                                sample_means["sample08"],
                                sample_cv["sample08"],
                                sample_concs["sample08"],
                                pos_neg["sample08"],

                            sample_dilution["sample09"].split("-")[0],
                                sample_means["sample09"],
                                sample_cv["sample09"],
                                sample_concs["sample09"],
                                pos_neg["sample09"],

                            sample_dilution["sample10"].split("-")[0],
                                sample_means["sample10"],
                                sample_cv["sample10"],
                                sample_concs["sample10"],
                                pos_neg["sample10"],

                            sample_dilution["sample11"].split("-")[0],
                                sample_means["sample11"],
                                sample_cv["sample11"],
                                sample_concs["sample11"],
                                pos_neg["sample11"],

                            sample_dilution["sample12"].split("-")[0],
                                sample_means["sample12"],
                                sample_cv["sample12"],
                                sample_concs["sample12"],
                                pos_neg["sample12"],

                            sample_dilution["sample13"].split("-")[0],
                                sample_means["sample13"],
                                sample_cv["sample13"],
                                sample_concs["sample13"],
                                pos_neg["sample13"],

                            sample_dilution["sample14"].split("-")[0],
                                sample_means["sample14"],
                                sample_cv["sample14"],
                                sample_concs["sample14"],
                                pos_neg["sample14"],

                            sample_dilution["sample15"].split("-")[0],
                                sample_means["sample15"],
                                sample_cv["sample15"],
                                sample_concs["sample15"],
                                pos_neg["sample15"],

                            sample_dilution["sample16"].split("-")[0],
                                sample_means["sample16"],
                                sample_cv["sample16"],
                                sample_concs["sample16"],
                                pos_neg["sample16"],

                            sample_dilution["sample17"].split("-")[0],
                                sample_means["sample17"],
                                sample_cv["sample17"],
                                sample_concs["sample17"],
                                pos_neg["sample17"],

                            sample_dilution["sample18"].split("-")[0],
                                sample_means["sample18"],
                                sample_cv["sample18"],
                                sample_concs["sample18"],
                                pos_neg["sample18"],

                            sample_dilution["sample19"].split("-")[0],
                                sample_means["sample19"],
                                sample_cv["sample19"],
                                sample_concs["sample19"],
                                pos_neg["sample19"],


                            sample_dilution["sample20"].split("-")[0],
                                sample_means["sample20"],
                                sample_cv["sample20"],
                                sample_concs["sample20"],
                                pos_neg["sample20"],

                            sample_dilution["sample21"].split("-")[0],
                                sample_means["sample21"],
                                sample_cv["sample21"],
                                sample_concs["sample21"],
                                pos_neg["sample21"],

                            sample_dilution["sample22"].split("-")[0],
                                sample_means["sample22"],
                                sample_cv["sample22"],
                                sample_concs["sample22"],
                                pos_neg["sample22"],

                            sample_dilution["sample23"].split("-")[0],
                                sample_means["sample23"],
                                sample_cv["sample23"],
                                sample_concs["sample23"],
                                pos_neg["sample23"],

                            sample_dilution["sample24"].split("-")[0],
                                sample_means["sample24"],
                                sample_cv["sample24"],
                                sample_concs["sample24"],
                                pos_neg["sample24"],

                            sample_dilution["sample25"].split("-")[0],
                                sample_means["sample25"],
                                sample_cv["sample25"],
                                sample_concs["sample25"],
                                pos_neg["sample25"],

                            sample_dilution["sample26"].split("-")[0],
                                sample_means["sample26"],
                                sample_cv["sample26"],
                                sample_concs["sample26"],
                                pos_neg["sample26"],

                            sample_dilution["sample27"].split("-")[0],
                                sample_means["sample27"],
                                sample_cv["sample27"],
                                sample_concs["sample27"],
                                pos_neg["sample27"],

                            sample_dilution["sample28"].split("-")[0],
                                sample_means["sample28"],
                                sample_cv["sample28"],
                                sample_concs["sample28"],
                                pos_neg["sample28"],

                            sample_dilution["sample29"].split("-")[0],
                                sample_means["sample29"],
                                sample_cv["sample29"],
                                sample_concs["sample29"],
                                pos_neg["sample29"],

                            sample_dilution["sample30"].split("-")[0],
                                sample_means["sample30"],
                                sample_cv["sample30"],
                                sample_concs["sample30"],
                                pos_neg["sample30"],

                            sample_dilution["sample31"].split("-")[0],
                                sample_means["sample31"],
                                sample_cv["sample31"],
                                sample_concs["sample31"],
                                pos_neg["sample31"],

                            sample_dilution["sample32"].split("-")[0],
                                sample_means["sample32"],
                                sample_cv["sample32"],
                                sample_concs["sample32"],
                                pos_neg["sample32"]
                            )

    html_file = plate_id + ".html"
    pdf_file = plate_id + ".pdf"

    with open(plate_id + ".html", 'w') as htmlfile:
        htmlfile.write(html_page)

    if include_pdf == "yes":
        print("Converting html to pdf...")
        pdfkit.from_file(html_file, pdf_file)

    shutil.move(html_file, os.path.join("html_reports", html_file))

### Output to csv ###
    print("Creating csv file")
    csv_file = plate_id + ".csv"

    with open(csv_file, "w") as csvfile:
        csvfile.write("sampleid, dilution, od, cv, abunits, posneg\n")
        for sample in ods.keys():
            if "sample" in sample:
                if sample_dilution[sample].split("-")[0] != "EMPTY":
                    csvfile.write(sample_dilution[sample].split("-")[0]
                                  + ", " + sample_dilution[sample].split("-")[1]
                                  + ", " + str(sample_means[sample])
                                  + ", " + str(sample_cv[sample])
                                  + ", " + str(sample_concs[sample])
                                  + ", " + pos_neg[sample] + "\n")
                else:
                    csvfile.write(sample_dilution[sample]
                                  + ", NA"
                                  + ", " + str(sample_means[sample])
                                  + ", " + str(sample_cv[sample])
                                  + ", " + str(sample_concs[sample])
                                  + ", " + pos_neg[sample] + "\n")



