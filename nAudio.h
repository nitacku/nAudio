/*
 * Copyright (c) 2017 nitacku
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
 * IN THE SOFTWARE.
 *
 * @file        nAudio.h
 * @summary     Audio library for noise and music
 * @version     1.2
 * @author      nitacku
 * @author      smbrown
 * @data        18 August 2018
 */

#ifndef _AUDIO_H_
#define _AUDIO_H_

#include <Arduino.h>
#include <inttypes.h>
#include <initializer_list.h>

// Global to reduce syntax clutter
static const uint16_t audio_note[] PROGMEM =
{
       1,
      65,   69,   73,   78,   82,   87,
      92,   98,  104,  110,  117,  123,    
     131,  139,  147,  156,  165,  175,
     185,  196,  208,  220,  233,  247,
     262,  277,  294,  311,  330,  349,
     370,  392,  415,  440,  466,  494,
     523,  554,  587,  622,  659,  698,
     740,  784,  831,  880,  932,  988,
    1046, 1109, 1175, 1245, 1319, 1397,
    1480, 1568, 1661, 1760, 1865, 1976,
    2093, 2217, 2349, 2489, 2637, 2794,
    2960, 3136, 3322, 3520, 3729, 3951,
    4186, 4435, 4699, 4978, 5274, 5588,
    5920, 6272, 6645, 7040, 7459, 7902,
    1500, 1525, 1550, 1575,
    1600, 1625, 1650, 1675,
};

enum NOTE : uint8_t
{
    NRS,
    NC2, NCS2, ND2, NDS2, NE2, NF2,
    NFS2, NG2, NGS2, NA2, NAS2, NB2,
    NC3, NCS3, ND3, NDS3, NE3, NF3,
    NFS3, NG3, NGS3, NA3, NAS3, NB3,
    NC4, NCS4, ND4, NDS4, NE4, NF4,
    NFS4, NG4, NGS4, NA4, NAS4, NB4,
    NC5, NCS5, ND5, NDS5, NE5, NF5,
    NFS5, NG5, NGS5, NA5, NAS5, NB5,
    NC6, NCS6, ND6, NDS6, NE6, NF6,
    NFS6, NG6, NGS6, NA6, NAS6, NB6,
    NC7, NCS7, ND7, NDS7, NE7, NF7,
    NFS7, NG7, NGS7, NA7, NAS7, NB7,
    NC8, NCS8, ND8, NDS8, NE8, NF8,
    NFS8, NG8, NGS8, NA8, NAS8, NB8,
    NS0, NS1, NS2, NS3,
    NS4, NS5, NS6, NS7,
    END, TEMPO,
    DTS, DS, DTE, DE, DTQ, DDE,
    DQ, DTH, DDQ, DH, DDH, DW,
    DBLIP,
};

static const uint16_t _BASE = 3; // Base duration

static const uint16_t audio_duration[] PROGMEM =
{
    (_BASE * 2 ) / 3, _BASE * 1, (_BASE * 4) / 3, _BASE * 2, (_BASE * 8) / 3, _BASE * 3,
    _BASE * 4, (_BASE * 16) / 3, _BASE * 6, _BASE * 8, _BASE * 12, _BASE * 16, 1,
};

class CAudio
{
    private:
    static const uint16_t FREQUENCY = 64000;
    static const uint8_t COUNT = 3;

    public:
    CAudio(uint8_t pin_0, uint8_t pin_1 = 0, uint8_t pin_2 = 0);

    typedef uint8_t (*StreamFunc)(uint16_t, void*);
    struct EndpointDescriptor
    {
        StreamFunc stream;
        void* context;
    };

    template<class... Contexts> void Play(StreamFunc stream, Contexts*... args)
    {
        Play({EndpointDescriptor{stream, const_cast<void*>(static_cast<const void*>(args))}...});
    };

    void Play(std::initializer_list<EndpointDescriptor> descriptors);
    void Stop(void);

    inline bool IsActive(void) __attribute__((always_inline))
    {
        return endpoint_count != 0;
    };

    //Poor man's namespace //TODO: maybe convenience function to shorten usage?
    struct Functions
    {
        static uint8_t NullStream(uint16_t, void*)
        {
            return NOTE::END;
        }

        static uint8_t PGMStream(uint16_t offset, void* data)
        {
            return pgm_read_word(((uint8_t*) data) + offset);
        }

        static uint8_t MemStream(uint16_t offset, void* data)
        {
            return ((uint8_t*) data)[offset];
        }
    };

    inline void InterruptMultipleStreams(void) __attribute__((always_inline));
    
    private:
    
    static uint8_t endpoint_count;
    
    class Endpoint
    {
        public:
        
        bool active = false;
        volatile uint8_t* port;
        uint8_t mask;
        
        private:
        
        uint8_t multiplier;
        uint8_t duration;
        uint16_t index;
        uint16_t ms_remaining;
        uint16_t period;
        uint16_t period_remaining;
        StreamFunc stream;
        void* context;
        
        public:
        
        Endpoint(void)
        {
            // Empty Constructor
        }

        void stop(void)
        {
            if(active)
            {
                active = false;
                endpoint_count--;
            }

            duration = DQ; // Default to quarter note
            *port &= ~mask; // Turn off pin
        }

        void assign(const EndpointDescriptor* descriptor)
        {
            stream = descriptor->stream;
            context = descriptor->context;
            stop(); // Place in default state
            active = true;
            multiplier = stream(0, context);
            
            index = 1;
            next(); // Calculate timing variables
        }

        private:

        void next(void)
        {
            uint8_t note_f;
            
            note_f = stream(index + 0, context);
            
            if (note_f < END)
            {
                uint16_t frequency = pgm_read_word(&(audio_note[note_f]));
                uint8_t next_value;
                
                next_value = stream(index + 1, context); // Look ahead
                
                // Check if value is a duration modifier
                if (next_value > TEMPO)
                {
                    duration = next_value;
                    index += 2;
                }
                else
                {
                    index += 1;
                }
                
                ms_remaining = multiplier * pgm_read_word(&(audio_duration[duration - TEMPO - 1]));

                period = FREQUENCY / frequency;
                period_remaining = period;
            }
            else if (note_f == TEMPO)
            {
                multiplier = stream(index + 1, context);
                
                index += 2;
                next(); // Fetch next note
            }
            else // End condition - Values outside of valid range fall here
            {
                stop();
            }
        }
        
        public: 
        
        inline void toggle(void) __attribute__((always_inline))
        {
            *port ^= mask; // Toggle pin
        }
        
        inline void tick(void) __attribute__((always_inline))
        {
            if (active)
            {
                if (--period_remaining == 0)
                {
                    period_remaining = period; // Reset period
                    toggle();
                }
            }
        }
        
        inline void tock(void) __attribute__((always_inline))
        {
            if (active)
            {
                if (--ms_remaining == 0)
                {
                    next();
                }
            }
        }
    };
    
    Endpoint endpoint[COUNT];
        
    inline void EnableInterrupt(void) __attribute__((always_inline))
    {
        TIMSK1 |= _BV(OCIE1A); // Enable timer compare interrupt
    }

    inline void DisableInterrupt(void) __attribute__((always_inline))
    {
        TIMSK1 &= ~_BV(OCIE1A); // Disable timer compare interrupt
    }
};

#endif
