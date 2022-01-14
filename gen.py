# this script generates a chord progression then a melody on top of it
# usage: python gen.py <MIN_BARS> <M/m>
# argv[2] should be M for major, m for minor

import sys
import random
import time
from mingus.core import intervals, scales
from mingus.core import chords as ch
from mingus.containers import NoteContainer, Note
from mingus.midi import fluidsynth

major_chords = [ "I", "ii", "iii", "IV", "V", "vi", "viio" ]
minor_chords = [ "i", "iio", "III", "iv", "V", "vi", "viio" ]
key_chords = major_chords

# what chords could feasibly come after this one
follows = [
    [1,2,3,4,5,6,7],
    [2,4,5,7],
    [2,3,4],
    [2,4,5,7],
    [1,6],
    [1,2,3,4,5,6,7],
    [1,5,6,7]
]

predominants = [ 2, 4 ]
dominants = [ 5, 7 ]

# number of times to reroll if you get this chord (easier probability manip)
reroll = [ 0, 1, 2, 0, 0, 1, 2 ]
# allow a duplicate chord (i.e. X -> X) _% of the time for this chord
# generally prefer movement, don't want static bassline
dupe_probs = [ 25, 5, 1, 15, 5, 10, 1 ]

chord_tones = [
    [1,3,5],
    [2,4,6],
    [3,5,7],
    [4,6,1],
    [5,7,2],
    [6,1,3],
    [7,2,4]
]
absolute_curr = 0

def ind(chord):
    return chord-1

# does the weird probability math i've set out here to get 
# an appropriately weighted rerolled chord
def reroll_chord(prev, chord):
    for _ in range(reroll[ind(chord)]):
        curr = random.choice(follows[ind(prev)])
        if curr != chord:
            # if reroll did not land same as before, reroll the new choice
            return reroll_chord(prev, curr)
    # if we got here, that means the chord rerolled itself 
    # the correct number of times and succeeded, can just return it
    return chord

# get rand chord and reroll if needed
def get_next_chord(curr):
    next_chord = reroll_chord(curr, random.choice(follows[ind(curr)]))
    while next_chord == curr:
        # keep it only if it passes the dick check
        if random.randint(0, 99) < dupe_probs[ind(next_chord)]:
            return next_chord
        # otherwise reroll it
        next_chord = reroll_chord(curr, random.choice(follows[ind(curr)]))
    return next_chord     

def generate_chord_prog(min_len):
    prog = [1]   
    # tap out when we have a "finishing" chord and we have at least the reqd # of chords
    while not (len(prog) >= min_len and prog[-1] in dominants):
        prog.append(get_next_chord(prog[-1]))
    return prog

# gets the note distance in lines on the staff
def get_note_distance(older, newer):
    # only weird cases are when we leap across the 7|1 boundary

    # account for leaps accross this boundary
    if newer == 1 and older in [4,6,7]:
        # 4, 6, or 7 to 1 is rising, treat 1 as an 8
        rval = 8 - older
        return rval
    if newer == 7 and older in [1,2,4]:
        # 1, 2, 4 to 7 is dropping, treat 7 as a 0
        rval = 0 - older
        return rval
    if older == 1 and newer in [7,6,4]:
        # 1 to 7,6,4 is dropping, treat 1 as an 8
        rval = newer - 8
        return rval
    if older == 7 and newer in [1,2,4]:
        # 7 to 1,2,4 is rising, treat 7 as a 0
        rval = newer - 0
        return rval
    # leaps of fifths that don't touch 7|1
    if older == 6 and newer == 3:
        rval = 4
        return rval
    if newer == 6 and older == 3:
        rval = -4
        return rval
    if older == 5 and newer == 2:
        rval = 4
        return rval
    if newer == 5 and older == 2:
        rval = -4
        return rval
    
    # otherwise it's trending down if newer < older
    rval = newer - older
    return rval

def is_trending_down(older, newer):
    return get_note_distance(older, newer) < 0

# build melody on top of it
# rules: step or leap on chord tones from prev, 
#   and note chosen must be consonant interval from bass note of chord
ABSOLUTE_CEILING = 8
ABSOLUTE_FLOOR = -8
def is_absolutely_viable(prev, proposed):
    global absolute_curr
    new_abs_curr = absolute_curr + get_note_distance(prev, proposed)
    down_trend = new_abs_curr < absolute_curr
    if down_trend and new_abs_curr < ABSOLUTE_FLOOR:
        return False
    return not (not down_trend and new_abs_curr > ABSOLUTE_CEILING)

# TODO allow leaps up into leaps down
def get_next_note(prev, curr, chord, consonant):
    global absolute_curr
    steps = [ curr+1, curr-1 ]
    if curr == 7:
        steps[0] = 1
    if curr == 1:
        steps[1] = 7

    # pick the option that makes a chord tone if we need consonance
    if consonant:
        for note in chord_tones[ind(chord)]:
            if note in steps and note != curr:
                # before making any decisions make sure it isn't going
                # too far from absolute zero
                if not is_absolutely_viable(curr, note):
                    continue
                absolute_curr += get_note_distance(curr, note)
                return note
        # only chord tone is the one we just used, leap to the next note
        next_note = random.choice(chord_tones[ind(chord)])
        while next_note == curr:
            next_note = random.choice(chord_tones[ind(chord)])
        # only place we allow it to potentially override our floor and ceiling
        absolute_curr += get_note_distance(curr, next_note)
        return next_note
    
    # if we have gone too far from absolute zero, bring us back
    if absolute_curr <= ABSOLUTE_FLOOR:
        absolute_curr += get_note_distance(curr, steps[0])
        return steps[0]
    if absolute_curr >= ABSOLUTE_CEILING:
        absolute_curr += get_note_distance(curr, steps[1])
        return steps[1]

    # if we don't need consonance, follow the trend of the last two notes
    if is_trending_down(prev, curr) and is_absolutely_viable(curr, steps[1]):                
        absolute_curr += get_note_distance(curr, steps[1])
        return steps[1]
    absolute_curr += get_note_distance(curr, steps[0])
    return steps[0]

def generate_measure(chord, prev_note, prev_prev_note):
    NOTES_PER_CHORD = 4
    measure = []
    absolute_measure = []
    # assume 4 notes per chord, try to make
    # first and last consonant -> [c ? ? c]
    for i in range(NOTES_PER_CHORD):
        temp = get_next_note(prev_prev_note, prev_note, chord, i == 0 or i == NOTES_PER_CHORD-1)
        # print("traveled from ", prev_note, " to ", temp, ", curr offset = ", absolute_curr)
        prev_prev_note = prev_note
        prev_note = temp
        measure.append(temp)
        absolute_measure.append(absolute_curr)
    return measure, absolute_measure, prev_note, prev_prev_note

def generate_notes(prog):
    global absolute_curr
    # song is chord -> notes over chord
    song = []
    absolutes = [[]]

    # do the first bar manually, annoying but necessary
    prev_prev_note = random.choice(chord_tones[ind(prog[0])])
    absolute_curr += get_note_distance(1, prev_prev_note)
    absolutes[-1].append(absolute_curr)
    prev_note = prev_prev_note+1
    if random.randint(0,1) == 0:
        # coin flip of going up or down to start
        prev_note = prev_prev_note-1
        if prev_note == 0:
            prev_note = 7
    song.append([prev_prev_note, prev_note])
    absolute_curr += get_note_distance(prev_prev_note, prev_note)
    absolutes[-1].append(absolute_curr)
    temp = get_next_note(prev_prev_note, prev_note, prog[0], False)
    absolutes[-1].append(absolute_curr)
    # print("traveled from ", prev_note, " to ", temp, ", curr offset = ", absolute_curr)
    prev_prev_note = prev_note
    prev_note = temp
    song[0].append(temp)
    temp = get_next_note(prev_prev_note, prev_note, prog[0], True)
    absolutes[-1].append(absolute_curr)
    # print("traveled from ", prev_note, " to ", temp, ", curr offset = ", absolute_curr)
    prev_prev_note = prev_note
    prev_note = temp
    song[0].append(temp)

    for i in range(1,len(prog)):
        measure, absolute_measure, prev_note, prev_prev_note = generate_measure(prog[i], prev_note, prev_prev_note)
        song.append(measure)
        absolutes.append(absolute_measure)
    return song, absolutes

def print_chords(prog, major = True):
    for c in prog:
        print(key_chords[ind(c)], end=" ")
    print("")

def generate_patternless_song(min_prog_len):
    # first make chord prog
    prog = generate_chord_prog(min_prog_len)
    # now we have our chord progression
    print_chords(prog)

    # song is chord -> notes over chord
    song, _ = generate_notes(prog)
    print(song)

def get_chord_str(chord):
    return key_chords[ind(chord)]

def get_inverted_str(chord):
    return get_chord_str(chord) + "6"

def get_third_of_chord(chord):
    return chord_tones[ind(chord)][1]

# takes in a chord prog (integers) and returns the smoothed
# version of the chord progression in roman numerals
def get_smoothed_bassline(prog, notes):
    roms = [ get_chord_str(prog[0]) ]
    old_base_correct = prog[0] == notes[0][0]
    new_base_correct = get_third_of_chord(prog[0]) == notes[0][0]
    is_base_correctness_better = new_base_correct and not old_base_correct
    if is_base_correctness_better:
        roms[0] = get_inverted_str(prog[0])

    # need to balance the following:
    #       note is the base of the chord +
    #       chord is a small distance from the prev
    for i in range(1, len(prog)):

        # if seventh, do it
        if prog[i] == 7:
            roms.append(get_inverted_str(prog[i]))
            continue

        # first see if we inverted the previous chord
        prev_inverted = roms[i-1][-1] == '6'

        old_bass_jump = 0
        new_bass_jump = 0
        if prev_inverted:
            old_bass_jump = abs(get_note_distance(get_third_of_chord(prog[i-1]), prog[i]))
            new_bass_jump = abs(get_note_distance(get_third_of_chord(prog[i-1]), get_third_of_chord(prog[i])))
        else: 
            old_bass_jump = abs(get_note_distance(prog[i-1], prog[i]))
            new_bass_jump = abs(get_note_distance(prog[i-1], get_third_of_chord(prog[i])))
        
        is_bass_jump_better = new_bass_jump < old_bass_jump
        old_base_correct = prog[i] == notes[i][0]
        new_base_correct = get_third_of_chord(prog[i]) == notes[i][0]
        is_base_correctness_better = new_base_correct and not old_base_correct

        # if both would be better inverted, do it
        if is_base_correctness_better:
            roms.append(get_inverted_str(prog[i]))
            continue

        # if base correctness neutral and bass jump better, do it
        if old_base_correct == new_base_correct and is_bass_jump_better:
            roms.append(get_inverted_str(prog[i]))
            continue

        # otherwise base correctness is better, invert it
        roms.append(get_chord_str(prog[i]))

    # never invert the final one
    roms[-1] = key_chords[0]
    return roms

def play_song(song_chords, song_notes):
    # play the song
    BAR_LENGTH = 2.0 # in seconds
    fluidsynth.init('/usr/share/sounds/sf2/FluidR3_GM.sf2',"alsa")
    key = "C"
    
    # generate scale and add octave information
    SCALE_OFFSET = 7
    scale = scales.Ionian(key, 4).ascending()
    for i in range(SCALE_OFFSET):
        scale[i] += '-2'
    for i in range(SCALE_OFFSET):
        scale[i+SCALE_OFFSET] += '-3'
    for i in range(SCALE_OFFSET):
        scale[i+2*SCALE_OFFSET] += '-4'
    for i in range(SCALE_OFFSET):
        scale[i+3*SCALE_OFFSET] += '-5'
    scale[-1] += '-6'
    print(scale)      
        
    note_ind = 0
    for chord in song_chords:
        # invert chords when called for
        inverted = False
        double_inverted = False
        if chord[-1] == '6':
            chord = chord[:-1]
            inverted = True
            if chord[-1] == 'o':
                chord = chord[:-1]
                double_inverted = True
            
        c = NoteContainer().from_progression_shorthand(chord, key)

        if inverted:
            c = ch.invert(c)
            if double_inverted:
                c = ch.invert(c)

        # print(c)
        fluidsynth.play_NoteContainer(c)

        # then play the bar
        if note_ind < len(song_notes) - 1:
            bar = song_notes[note_ind]
            note_ind += 1
            for note in bar:
                
                note = Note(scale[note + 2*SCALE_OFFSET])
                fluidsynth.play_Note(note)
                
                # sleep an even amount of time between notes
                time.sleep(BAR_LENGTH/len(bar))
                fluidsynth.stop_Note(note)

        else:
            # play the whole note at end of song
            note = Note(scale[song_notes[-1][0] + 2*SCALE_OFFSET])
            fluidsynth.play_Note(note)
            time.sleep(BAR_LENGTH)
            fluidsynth.stop_Note(note)
        
        # stop the chord for the next bar
        fluidsynth.stop_NoteContainer(c)

def main():
    # annoying setup code
    major = True
    if len(sys.argv) > 2:
        major = (sys.argv[2] == "M")

    MIN_PRO_LEN = 16
    if len(sys.argv) > 1:
        MIN_PROG_LEN = int(sys.argv[1])

    if "-h" in sys.argv or "--help" in sys.argv:
        print("usage: python gen.py <MIN_BARS> <M/m>")
        sys.exit()

    global absolute_curr
    global key_chords
    if (not major):
        key_chords = minor_chords
            
    # make patterns of length 4 or 8 with viable chord prog
    # then do ABA structure, final A slightly changed for effect
    # make sure the patterns have a climax

    # just use the existing functionality and check to see if it
    # happens to meet the above criteria
    PATTERN_LEN = 4
    a_chords = []
    while len(a_chords) != PATTERN_LEN:
        a_chords = generate_chord_prog(PATTERN_LEN)
    a_notes, a_abs = generate_notes(a_chords)

    b_chords = []
    while len(b_chords) != PATTERN_LEN or b_chords == a_chords:
        b_chords = generate_chord_prog(PATTERN_LEN)
    b_notes, b_abs = generate_notes(b_chords)

    # print("<A>: ", a_chords)
    # print("<B>: ", b_chords) # TODO fix the note distance function or how absolute curr is updated

    song_chords = []
    song_chords.extend(a_chords)
    song_chords.extend(b_chords)
    song_chords.extend(a_chords)

    song_notes = []
    song_notes.extend(a_notes)
    song_notes.extend(b_notes)
    song_notes.extend(a_notes)
    
    absolute_notes = []   
    absolute_notes.extend(a_abs)
    absolute_notes.extend(b_abs) # TODO right here use note distance to make the second a_abs add not a huge leap
    absolute_notes.extend(a_abs)

    # if doesn't end on a 1, append so it now does (chords & notes)
    # because the a section must always end on a pretonic, we need max of one bar
    # to get to a 1 in terms of chords and notes
    if song_chords[-1] != 1:
        # but ending on a whole note is also good, why bother for now
        song_chords.append(1)
        absolute_curr += get_note_distance(song_notes[-1][-1], 1)
        song_notes.append([1])
        absolute_notes.append([absolute_curr])

    # have our basic song with structure now
    # now go through and invert shit, smooth out the bassline as much as possible
    song_chords = get_smoothed_bassline(song_chords, song_notes) # TODO less I -> V -> I -> V please
    print(song_chords)
    print(song_notes)
    print(absolute_notes)

    # ...and change the rhythm to be more exciting
    # change chord rhythm for b section?

    play_song(song_chords, absolute_notes)

if __name__ == '__main__':
    main()
