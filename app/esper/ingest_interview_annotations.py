from esper.prelude import *
from query.models import Video, LabeledCommercial, LabeledPanel, LabeledInterview
import sys
import csv

'''
This module parses four tsv's to get labeled interviews, panels, and
commercials.

The four tsv's it expects:
    * named_interviews:
        First row: three columns "Video ID", "Name", "Default Interview"
        Later rows: minimum of three columns
            first column is video ID
            second column is the video name
            third column is either "none" or "interviewer name, guest name"
            fourth column and beyond are interview strings of the format:

            [["Clips of "|"(originally from a different show) "]
                [interviewer1[, interviewer2] * ]guest1[, guest2] ]
                int [[hh:]m]m:ss-[[hh:]m]m:ss

    * interviews:
        First row: two columns "Video ID", "Name"
        Later Rows: minimum of two columns
            first column is video ID
            second column is video name
            third column and beyond are interview strings of the format:

            int [[hh:]m]m:ss-[[hh:]m]m:ss

    * panels:
        First row: two columns "Video ID", "Name"
        Later Rows: minimum of two columns
            first column is video ID
            second column is video name
            third column and beyond are panel strings of the format:

            panel(n) [[hh:]m]m:ss-[[hh:]m]m:ss
    
    * commercials:
        First row: two columns "Video ID", "Name"
        Later Rows: minimum of two columns
            first column is video ID
            second column is video name
            third column and beyond are commercial strings of the format:

            comm [[hh:]m]m:ss-[[hh:]m]m:ss
'''

def eprint(string):
    print(string, file=sys.stderr)

def parse_time_to_seconds(timestamp):
    # time format is [[hh:]m]m:ss
    units = timestamp.split(':')
    num_seconds = 0
    if len(units) == 3:
        return int(units[0]) * 3600 + int(units[1]) * 60 + int(units[2])
    elif len(units) == 2:
        return int(units[0]) * 60 + int(units[1])
    else:
        eprint("Time format not understood! {}".format(timestamp))
        sys.exit(1)

def parse_time_range_to_seconds(timerange):
    # time range format is [[hh:]m]m:ss-[[hh:]m]m:ss
    start_time, end_time = timerange.split('-')
    start = parse_time_to_seconds(start_time)
    end = parse_time_to_seconds(end_time)

    if end <= start:
        eprint("Start time not before end time! {}".format(timerange))
        sys.exit(1)

    return start, end

def parse_interview_names(interview_names):
    # parsing interviewer1[, interviewer2] * ]guest1[, guest2] 
    names = {
        'interviewer1': '',
        'interviewer2': '',
        'guest1': '',
        'guest2': ''
    }

    if '*' in  interview_names:
        interviewers, guests = interview_names.split('*')

        if ',' in interviewers:
            interviewer1, interviewer2 = interviewers.split(',')
            names['interviewer1'] = interviewer1.lower().strip()
            names['interviewer2'] = interviewer2.lower().strip()
        else:
            name = interviewers.lower().strip()
            if name != 'interviewer':
                names['interviewer1'] = name

        if ',' in guests:
            guest1, guest2 = guests.split(',')
            names['guest1'] = guest1.lower().strip()
            names['guest2'] = guest2.lower().strip()
        else:
            names['guest1'] = guests.lower().strip()
    else:
        names['guest1'] = interview_names.lower().strip()

    return names

def parse_commercial(commercial_string, video_id):
    # expecting comm [[hh:]m]m:ss-[[hh:]m]m:ss
    commercial_string = commercial_string.lower()
    label, timerange = commercial_string.split()
    if label == 'comm':
        comm = LabeledCommercial()

        start, end = parse_time_range_to_seconds(timerange)
        comm.start = start
        comm.end = end
        comm.video = video_id

        return comm
    else:
        eprint("Commercial string can't be parsed! {}".format(
            commercial_string))
        sys.exit(1)

def parse_panel(panel_string, video_id):
    # expecting panel(n) [[hh:]m]m:ss-[[hh:]m]m:ss
    panel_string = panel_string.lower()
    label, timerange = panel_string.split()
    panel_label = 'panel('
    if label.startswith(panel_label):
        panel = LabeledPanel()

        num_panelists = int(label[len(panel_label):len(label)-1])
        panel.num_panelists = num_panelists
        
        start, end = parse_time_range_to_seconds(timerange)
        panel.start = start
        panel.end = end
        panel.video = video_id

        return panel
    else:
        eprint("Panel string can't be parsed! {}".format(panel_string))
        sys.exit(1)
    
def parse_interview_with_names(interview_string, video_id,
        default_interviewer=None, default_guest=None):
    '''
    expecting this (newlines do not denote whitespace):

        [["Clips of "|"(originally from a different show) "]
            [interviewer1[, interviewer2] * ]guest1[, guest2] ]
            int [[hh:]m]m:ss-[[hh:]m]m:ss
    '''
    interview_string = interview_string.lower()

    interview_label = 'int '

    if interview_label not in interview_string:
        eprint("Interview string can't be parsed! {}".format(interview_string))
        sys.exit(1)

    interview = LabeledInterview()
    interview.video = video_id
    interview.interviewer1 = default_interviewer
    interview.guest1 = default_guest
    
    clips_string = "clips of"
    if interview_string.startswith(clips_string):
        interview.scattered_clips = True
        interview.original = False
        interview_string = interview_string[len(clips_string):].strip()

    unoriginal_string = "(originally from a different show) "
    if interview_string.startswith(unoriginal_string):
        interview.original = False
        interview_string = interview_string[len(unoriginal_string):].strip()

    if interview_string.startswith(interview_label):
        time_range = interview_string[len(interview_label):]
    else:
        name_string, time_range = interview_string.split(' ' + interview_label)
        names = parse_interview_names(name_string)

        if names['interviewer1'] != '':
            interview.interviewer1 = names['interviewer1']
            if names['interviewer2'] != '':
                interview.interviewer2 = names['interviewer2']
        if names['guest1'] != '':
            interview.guest1 = names['guest1']
            if names['guest2'] != '':
                interview.guest2 = names['guest2']

    start, end = parse_time_range_to_seconds(time_range)
    interview.start = start
    interview.end = end

    return interview
        
def parse_interview_no_names(interview_string, video_id):
    # expecting int [[hh]m]m:ss-[[hh]m]m:ss
    interview_string = interview_string.lower()
    label, timerange = interview_string.split()
    if label == 'int':
        interview = LabeledInterview()

        start, end = parse_time_range_to_seconds(timerange)
        interview.start = start
        interview.end = end
        interview.video = video_id

        return interview
    else:
        eprint("interview string can't be parsed! {}".format(
            interview_string))
        sys.exit(1)

def parse_named_interview_row(row):
    video_id = int(row[0])
    video = Video.objects.get(pk=video_id)
    default_names = row[2]
    default_interviewer = None
    default_guest = None
    if default_names != 'none':
        default_interviewer, default_guest = default_names.split(', ')
        default_interviewer = default_interviewer.lower().strip()
        default_guest = default_guest.lower().strip()

    interviews = []

    if len(row) > 3:
        for interview_string in row[3:]:
            if interview_string != '':
                interview = parse_interview_with_names(interview_string, video,
                        default_interviewer, default_guest)
                interviews.append(interview)

    return interviews

def parse_row_simple(row, parse_fn):
    video_id = int(row[0])
    video = Video.objects.get(pk=video_id)

    items = []
    if len(row) > 2:
        for item_string in row[2:]:
            if item_string != '':
                items.append(parse_fn(item_string, video))

    return items

def parse_interview_row(row):
    return parse_row_simple(row, parse_interview_no_names)
def parse_panel_row(row):
    return parse_row_simple(row, parse_panel)
def parse_commercial_row(row):
    return parse_row_simple(row, parse_commercial)

def read_tsv(tsvname, first_row, row_parser):
    items = []
    with open(tsvname, 'r') as tsvfile:
        reader = csv.reader(tsvfile, delimiter='\t')
        row1 = next(reader)
        if len(row1) < len(first_row) or row1[:len(first_row)] != first_row:
            eprint("TSV format is wrong! {}, {}".format(tsvname, row1))
            sys.exit(1)
        
        for row in reader:
            items.extend(row_parser(row))

    return items

def read_alltsvs(named_interview_file, interview_file, panel_file,
        commercial_file):
    interviews = []
    interviews.extend(read_tsv(named_interview_file,
        ["Video ID", "Name", "Default Interview"], parse_named_interview_row))
    interviews.extend(read_tsv(interview_file, ["Video ID", "Name"],
        parse_interview_row))

    panels = read_tsv(panel_file, ["Video ID", "Name"], parse_panel_row)
    commercials = read_tsv(commercial_file, ["Video ID", "Name"],
        parse_commercial_row)

    return interviews, panels, commercials

def parse_tsvs():
    folder_path = "/app/data/labeled_interviews/"
    named_interview_file = folder_path + "named_interviews.tsv"
    interview_file = folder_path + "interviews.tsv"
    panel_file = folder_path + "panels.tsv"
    commercial_file = folder_path + "commercials.tsv"

    interviews, panels, commercials = read_alltsvs(named_interview_file,
            interview_file, panel_file, commercial_file)

    return interviews, panels, commercials

def clear_all():
    LabeledInterview.objects.all().delete()
    LabeledPanel.objects.all().delete()
    LabeledCommercial.objects.all().delete()

def commit(interviews, panels, commercials):
    LabeledInterview.objects.bulk_create(interviews)
    LabeledPanel.objects.bulk_create(panels)
    LabeledCommercial.objects.bulk_create(commercials)
