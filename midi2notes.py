#!/usr/bin/python

import argparse, os, collections, bisect, platform
import midi
from itertools import islice
from fractions import gcd
from glob import glob


notes = ["NC2", "NCS2", "ND2", "NDS2", "NE2", "NF2",
         "NFS2", "NG2", "NGS2", "NA2", "NAS2", "NB2",
         "NC3", "NCS3", "ND3", "NDS3", "NE3", "NF3",
         "NFS3", "NG3", "NGS3", "NA3", "NAS3", "NB3",
         "NC4", "NCS4", "ND4", "NDS4", "NE4", "NF4",
         "NFS4", "NG4", "NGS4", "NA4", "NAS4", "NB4",
         "NC5", "NCS5", "ND5", "NDS5", "NE5", "NF5",
         "NFS5", "NG5", "NGS5", "NA5", "NAS5", "NB5",
         "NC6", "NCS6", "ND6", "NDS6", "NE6", "NF6",
         "NFS6", "NG6", "NGS6", "NA6", "NAS6", "NB6",
         "NC7", "NCS7", "ND7", "NDS7", "NE7", "NF7",
         "NFS7", "NG7", "NGS7", "NA7", "NAS7", "NB7",
         "NC8", "NCS8", "ND8", "NDS8", "NE8", "NF8",
         "NFS8", "NG8", "NGS8", "NA8", "NAS8", "NB8"]

duration_strings = [
    "DTS", "DS", "DTE", "DE", "DTQ", "DDE",
    "DQ", "DTH", "DDQ", "DH", "DDH", "DW"
]

value_dict = {"":"", "NRS": 0}

verbose = 0
noteEncountered = False
tempoChanges = False
totalSaved = 0
totalBytes = 0

def main():
    global verbose

    parser = argparse.ArgumentParser(description='Output clock compatible data from a midi file.')
    parser.add_argument('files', metavar='file', type=str, nargs='+',
                       help='a midi file to read from')
    parser.add_argument('-O', '--optimize', action='store_true', help='Use optimize status')
    parser.add_argument('-o', '--output', help='File to output to')
    parser.add_argument('-j', '--json', action='store_true', help='Use JSON format')
    parser.add_argument("-v", "--verbosity", action="count", default=0, help='Each use increases verbosity level')

    args = parser.parse_args()
    
    verbose = args.verbosity

    if verbose > 0:
        print args

    if args.output:
        outFile = open(args.output, 'wb+') # Open byte-wise to ensure consistent line endings
        outFile.write("[\n")
    else:
        outFile = None

    files = []
    
    # Fix stupid Windows non-expanding wildcard bug
    if platform.system() == 'Windows':
        for file in args.files:
            files += glob(file)
    else:
        files = args.files
    
    for f in files:
        print "Now processing: " + f
        processFile(f, optimize=args.optimize, printJSON=args.json, outFile=outFile);

    if args.output:
        outFile.seek(-2, os.SEEK_END)
        outFile.truncate() # Remove trailing comma
        outFile.write("\n]\n")

    if args.optimize and len(files) > 1:
        fmtString = 'Total bytes saved from optimization: {}/{} ({:.2f}%)'
        print fmtString.format(totalSaved, totalBytes, (totalSaved*100.0)/totalBytes)

def window(seq, n=2):
    it = iter(seq)
    result = tuple(islice(it, n))
    if len(result) == n:
        yield result
    for elem in it:
        result = result[1:] + (elem,)
        yield result

def initValueDict():
    i = 1
    for note in notes:
        value_dict[note] = i
        i += 1

    i+= 8
    value_dict["END"] = i

    i+= 1
    value_dict["TEMPO"] = i

    i+= 1
    for duration in duration_strings:
        value_dict[duration] = i
        i += 1


#sorts events such that meta < noteoff < noteon w/ 0 vel < noteon
#other types will sort below/above noteon/off depending on their midi value
def eventSort(x, y):
    if x.statusmsg == 0xFF and y.statusmsg != 0xFF:
        return -1
    elif y.statusmsg == 0xFF and x.statusmsg != 0xFF:
        return 1

    if x.statusmsg > y.statusmsg:
        return 1
    elif x.statusmsg <  y.statusmsg:
        return -1
    elif x.statusmsg == 0x90 and y.statusmsg == 0x90:
        if x.velocity > y.velocity:
            return 1
        elif x.velocity < y.velocity:
            return -1
        else:
            return 0
    else:
        return 0


def processFile(filename, optimize=False, numChannels=2, printJSON=False, outFile=None):
    global noteEncountered, tempoChanges
    if verbose > 2:
        print "Entering processFile()"

    noteEncountered = False
    tempoChanges = False

    pattern = midi.read_midifile(filename)

    pattern.make_ticks_abs()

    if verbose > 2:
        print pattern
        print '\n'

    channels = []

    for i in range(numChannels):
        channels.append({"Busy": False, "Pending":(), "Notes": []})

    #Flattens to a single list
    events = [item for sublist in pattern for item in sublist]

    #Because sorting is stable we can sort on type and then timestamp to ensure off's come
    # before equivalent tick on events
    events = sorted(events, cmp=eventSort)
    events = sorted(events, key=lambda x: x.tick)

    for e in events:
        processEvent(e, channels)

    if verbose > 2:
        print '\n'

    #TODO: doesn't work yet
    #if not tempoChanges:
    #    resolution = checkResolution(channels, pattern.resolution/4)
    #else:
    resolution = pattern.resolution/(4*3)

    uspq = channels[0].get("Tempo", 500000)
    tsD = channels[0].get("TimeSignature", 4.0)

    multiplier = calculateTiming(channels, pattern.resolution, uspq=uspq, tsDenominator=tsD)

    #Just need the notes now, can drop all other information
    for i in range(len(channels)):
        channels[i] = channels[i]["Notes"]

    #Prune empty channels
    channels = [x for x in channels if x]

    if verbose > 0 and len(channels) != numChannels:
        print "NOTE: Pruned at least one empty channel"

    channels = insertRests(channels, resolution)
    channels = splitLongNotes(channels, resolution)
    channels = convertDurations(channels, resolution)

    doSanityChecks(channels)

    if optimize: 
        channels = doOptimize(channels)

    printResult(channels, multiplier, filename, json=printJSON, outFile=outFile)

    if verbose > 2:
        print "Exiting processFile()\n"


def processEvent(event, channels):
    global noteEncountered, tempoChanges

    if len(channels) <= 0:
        raise ValueError("There must be at least one channel")

    if event.statusmsg == 0x90 and event.velocity > 0:
        noteEncountered = True
        processNoteOn(event, channels)

    elif event.statusmsg == 0x90 and event.velocity == 0:
        processNoteOff(event, channels)

    elif event.statusmsg == 0x80:
        processNoteOff(event, channels)

    elif event.statusmsg == 0xFF and event.metacommand == 0x51: #set tempo event
        if noteEncountered:
            tempo = ("TEMPO", event.tick, event.tick, event.get_mpqn())
            if verbose > 2:
                print "Tempo change:", tempo

            for channel in channels:
                channel["Notes"].append(tempo)
                tempoChanges = True
        else:
            channels[0]["Tempo"] = event.get_mpqn()
            print "Tempo event, new uS/Q:", channels[0]["Tempo"]

    elif event.statusmsg == 0xFF and event.metacommand == 0x58: #time signature event
        channels[0]["TimeSignature"] = event.get_denominator()
        if verbose > 2:
            print "Time signature event, new denominator:", channels[0]["TimeSignature"]

def processNoteOn(note, channels):
    pitch = notes[note.get_pitch()-24]
    if verbose > 2:
        print pitch, "on:", note.tick

    #add to first available channel
    for channel in channels:
        if not channel["Busy"]:
            channel["Busy"] = True
            channel["Pending"] = (pitch, note.tick, 0)
            return

    print "WARNING: All channels busy; dropping note..."


def processNoteOff(note, channels):
    pitch = notes[note.get_pitch()-24]

    if verbose > 2:
        print pitch, "off:", note.tick

    #Find corresponding note
    for channel in channels:
        if channel["Busy"]:
            pending = channel["Pending"]
            if pending[0] == pitch:
                channel["Busy"] = False
                channel["Notes"].append((pitch, pending[1], note.tick))
                channel["Pending"] = ()
                return

    print "WARNING: Can't find corresponding note..."

def checkResolution(channels, resolution):
    if verbose > 2:
        print "Entering checkResolutions()"

    g = []
    for i in range(len(channels)):
        durations = map(lambda w: w[1][1] - w[0][1], window(channels[i]["Notes"]))
        g.append(reduce(gcd, durations, resolution))

    r = reduce(gcd, g)

    if verbose > 2:
        print 'GCD: {}\nGCD % resolution ({}): {}'.format(r, resolution, r % resolution)

    if r % resolution != 0:
        print "WARNING: Something may be wrong with durations, attempting to correct"

        factor = 2
        distance = abs(resolution - r)
        while distance > abs(resolution - (r / factor)) and factor <= 4:
            distance = abs(resolution - (r / factor))
            factor *= 2

        factor /= 2

        print "WARNING: Adjusting resolution to", r/factor
        if verbose > 2:
            print "Exiting checkResolutions()\n"
        return r/factor
    else:
        if verbose > 2:
            print "Exiting checkResolutions()\n"
        return resolution

def calculateTiming(channels, patternResolution, uspq=500000, tsDenominator=4.0):
    if verbose > 2:
        print "Entering calculateTiming()"

    SecondsPerQuarterNote = uspq / 1000000.0
    SecondsPerTick = SecondsPerQuarterNote / patternResolution

    bpm = (60000000 / uspq) * (tsDenominator / 4.0)
    multiplier = int(uspq/12000) #BASE quarter length is 12ms

    if verbose > 0:
        print "Tick Length (s)", SecondsPerTick
        print "Sixteenth note duration set to", patternResolution/4, "ticks"
        print "Length of sixteenth", (SecondsPerTick*patternResolution)/4
        print "uS/Q", uspq

    print "BPM", bpm
    print "Multiplier", multiplier

    if verbose > 2:
        print "Exiting calculateTiming()\n"
    return multiplier


def insertRests(channels, resolution):
    if verbose > 2:
        print "Entering insertRests()"

    tempChannels = []
    for channel in channels:
        tempChannel = []

        #check if the first channel should start with a rest
        if channel[0][1] != 0:
            n = ('NRS', 0, channel[0][1])
            tempChannel.append(n)

            if verbose > 2:
                print "Adding rest to beginning of channel"
                print n

        for w in window(channel):
            #if (start of note - prev note's stop) < 2*resolution then a rest is needed
            if (w[1][1] - w[0][2]) >= 2*resolution:
                #TODO: There may be a case or two where this won't work, needs more testing
                restLength = int((w[1][1] - w[0][2])/resolution)*resolution #erode/dialate

                n = ('NRS', w[1][1]-restLength, w[1][1])

                if w[0][0] is not "TEMPO":
                    t = (w[0][0], w[0][1], n[1])
                else:
                    t = w[0]

                tempChannel.append(t)
                tempChannel.append(n)

                if verbose > 2:
                    print t
                    print n

            else:
                if w[0][0] is not "TEMPO":
                    t = (w[0][0], w[0][1], w[1][1])
                else:
                    t = (w[0][0], w[0][1], w[1][1], w[0][3])
                tempChannel.append(t)

                if verbose > 2:
                    print t

        #fix timing and append the final note
        n = (
            channel[-1][0],
            channel[-1][1],
            int(resolution * round(float(channel[-1][2])/resolution))
        )
        tempChannel.append(n)
        tempChannels.append(tempChannel)

    if verbose > 1:
        print '\n'

    if verbose > 2:
        print "Exiting insertRests()\n"

    return tempChannels

#TODO: squash small repeated notes since we don't add silence?
#TODO: swap notes between channels if possible to maximize runs of similar durations?
def doOptimize(channels):
    global totalSaved, totalBytes

    if verbose > 2:
        print "Entering doOptimize()"

    tempChannels = []

    songSaved = 0
    songBytes = 0

    for channel in channels:
        tempChannel = []
        tempDuration = ''
        songBytes += 2*len(channel)
        for note in channel:
            if tempDuration == note[1]:
                tempChannel.append((note[0] , ''))
                songSaved += 1
            else:
                tempChannel.append(note)
                tempDuration = note[1]
        tempChannels.append(tempChannel)

    fmtString = 'Bytes saved from optimization pass: {}/{} ({:.2f}%)'
    outString = fmtString.format(songSaved, songBytes, (songSaved*100.0)/songBytes)
    print outString

    totalSaved += songSaved
    totalBytes += songBytes

    if verbose > 2:
        print "Exiting doOptimize()\n"
    return tempChannels


def splitLongNotes(channels, resolution):
    if verbose > 2:
        print "Entering splitLongNotes()"

    tempChannels = []
    for channel in channels:
        tempChannel = []
        for note in channel:
            duration = note[2]-note[1]

            if note[2]-note[1] > resolution*48:
                if verbose > 1:
                    print "WARNING: found note too long,", note

                split = []
                offset = note[1]
                while duration != 0:
                    if duration % resolution != 0 or duration < resolution*2:
                        print "WARNING: no way to split note, duration not a multiple of resolution"

                    if duration > resolution*48:
                        duration -= resolution*48
                        split.append((note[0], offset, offset+resolution*48))
                        offset += resolution*48
                    else:
                        split.append((note[0], offset, offset+duration))
                        duration -= duration

                if verbose > 1:
                    print "Split long note into:", split
                tempChannel.extend(split)

            else:
                tempChannel.append(note)
        tempChannels.append(tempChannel)
                

    if verbose > 2:
        print "Exiting splitLongNotes()\n"

    return tempChannels


def convertDurations(channels, resolution):
    if verbose > 2:
        print "Entering convertDurations()"

    durations = collections.OrderedDict([
        (resolution *  2, "DTS"),
        (resolution *  3, "DS"),
        (resolution *  4, "DTE"),
        (resolution *  6, "DE"),
        (resolution *  8, "DTQ"),
        (resolution *  9, "DDE"),
        (resolution * 12, "DQ"),
        (resolution * 16, "DTH"),
        (resolution * 18, "DDQ"),
        (resolution * 24, "DH"),
        (resolution * 36, "DDH"),
        (resolution * 48, "DW"),
    ])

    if verbose > 1:
        print "Sixteenth resolution", resolution * 3
        print "Durations", durations

    tempChannels = []
    for channel in channels:
        tempChannel = []
        for note in channel:
            ind = bisect.bisect_left(durations.keys(), (note[2] - note[1]))

            if (note[2] - note[1]) != durations.keys()[ind] and note[0] is not "TEMPO":
                notes = handleOddDuration(durations, resolution, note)

                if verbose > 1:
                    print "WARNING: Odd duration", note, "->", notes

                for n in notes:
                    tempChannel.append(n)

                continue


            if note[0] is not "TEMPO":
                newNote = (note[0], duration_strings[ind])
            else:
                #BASE quarter length is 12ms
                newNote = (note[0], str(int(note[3]/12000)))

            if verbose > 2:
                print note, note[2]-note[1], ind, "->", newNote

            tempChannel.append(newNote)
        tempChannels.append(tempChannel)

    if verbose > 2:
        print "Exiting convertDurations()\n"
    return tempChannels


def handleOddDuration(durations, resolution, note):
    if verbose > 2:
        print "Entering handleOddDuration()"

    ind = bisect.bisect_left(durations.keys(), (note[2] - note[1]))
    temp = []

    #TODO: up the verbosity level on this?
    if verbose > 2:
        print "len(actual), len(note), delta, resolution"
        print (note[2] - note[1]), durations.keys()[ind], durations.keys()[ind] - (note[2] - note[1]), resolution
        print note

    #TODO: this doesn't work if the duration is < 2*resolution

    remaining = -1
    while remaining != 0 and ind > 0:
        remaining = (note[2] - note[1])
        i = ind - 1
        temp = []
        while remaining != 0 and i >= 0:
            if durations.keys()[i] <= remaining:
                temp.append((note[0], duration_strings[i]))
                remaining = remaining - durations.keys()[i]
            else:
                i = i - 1
        ind = ind - 1

    if verbose > 2:
        print "Exiting handleOddDuration()\n"
    return temp


def doSanityChecks(channels):
    if verbose > 2:
        print "Entering doSanityChecks()"

    durations = dict([
        ("DTS",  2),
        ("DS",   3),
        ("DTE",  4),
        ("DE",   6),
        ("DTQ",  8),
        ("DDE",  9),
        ("DQ",  12),
        ("DTH", 16),
        ("DDQ", 18),
        ("DH",  24),
        ("DDH", 36),
        ("DW",  48),
    ])

    lengths = []

    for channel in channels:
        l = 0
        for note in channel:
            if note[0] is not "TEMPO":
                l += durations[note[1]]
        lengths.append(l)

    if lengths.count(lengths[0]) != len(lengths):
        print "WARNING: Track lengths differ (may not be an issue):", lengths

    if verbose > 2:
        print "Exiting doSanityChecks()\n"

def printResult(channels, multiplier, filename, json=False, outFile=None):
    print"\n"
    if not outFile:
        print "===================================================================="
        print "Begin Output for " + filename
        print "====================================================================\n"

    if json:
        printResultJSON(channels, multiplier, filename, outFile=outFile)
    else:
        printResultString(channels, multiplier, filename, outFile=outFile)

    if not outFile:
        print "===================================================================="
        print "End Output for " + filename
        print "====================================================================\n"

def printResultJSON(channels, multiplier, filename, outFile=None):
    name = os.path.splitext(os.path.basename(filename))[0]

    outString = "{\n"
    outString += '    "Filename": "' + name + '",\n'

    count = 0
    for channel in channels:
        outString += '    "Channel_' + str(chr(count + ord('A'))) + '": [\n'
        outString += '                   ' + str(multiplier) + ', '
        i = 2

        for note in channel:
            if i >= 16: #16 is good width for 100 column editors
                ninth = "\n                   "
                i = 0
            else:
                ninth = " "

            if note[1] is '':
                outString += '{},{}'.format(value_dict[note[0]], ninth)
                i += 1
            elif note[0] is 'TEMPO':
                outString += '{}, {},{}'.format(value_dict[note[0]], note[1], ninth)
                i += 2
            else:
                outString += '{}, {},{}'.format(value_dict[note[0]], value_dict[note[1]], ninth)
                i += 2

        outString += str(value_dict["END"]) + '\n                 ]'
        # Don't add comma to last entry
        if count < len(channels) - 1:
            outString += ','
        outString += '\n'
        count += 1

    outString += "},\n"

    if outFile:
        outFile.write(outString)
    else:
        print outString

def printResultString(channels, multiplier, filename, outFile=None):
    count = ord('A')
    name = os.path.splitext(os.path.basename(filename))[0]

    for channel in channels:
        print "static const uint8_t music_" + str(name) + "_" + str(chr(count)) + "[] PROGMEM ="
        print "{"
        print "    ", str(multiplier) + ",",
        i = 1
        for note in channel:
            if i >= 16: #16 is good width for 100 column editors
                ninth = "\n    "
                i = 0
            else:
                ninth = ""

            if note[1] is '':
                outString = '{},{}'.format(note[0], ninth)
                i += 1
            else:
                outString = '{}, {},{}'.format(note[0], note[1], ninth)
                i += 2

            print outString,
        print "END"
        print "};\n"
        count += 1

    outstring = '    {'
    for c in range(ord('A'), count):
        outstring += "music_" + str(name) + "_" + str(chr(c)) + ', '
    outstring = outstring[:-2] + "},\n"
    print outstring

    if outFile:
        print "WARNING: Writing c format to file currently not supported"


initValueDict()
if __name__ == "__main__":
    main()
