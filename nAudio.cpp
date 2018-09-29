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
 * @file        nAudio.cpp
 * @summary     Audio library for noise and music
 * @version     1.2
 * @author      nitacku
 * @author      smbrown
 * @data        18 August 2018
 */
 
#include "nAudio.h"

static CAudio* g_callback_object = nullptr; // Global pointer to class object

//Why this can't be in a .h file is beyond me, C++ is screwy
uint8_t CAudio::endpoint_count = 0;

CAudio::CAudio(uint8_t pin_0, uint8_t pin_1, uint8_t pin_2)
{
    uint8_t pin_array[COUNT] = {pin_0, pin_1, pin_2};
    
    for (uint8_t index = 0; index < COUNT; index++)
    {
        if (pin_array[index])
        {
            uint8_t pin = pin_array[index];
            endpoint[index].mask = digitalPinToBitMask(pin); // Port register bitmask
            endpoint[index].port = portOutputRegister(digitalPinToPort(pin));  // Output port register
            
            uint8_t *_pinMode = (uint8_t *) portModeRegister(digitalPinToPort(pin)); // Port mode register
            *_pinMode |= endpoint[index].mask; // Set the pin to Output mode
        }
    }
    
    g_callback_object = this;
}

void CAudio::Play(std::initializer_list<EndpointDescriptor> descriptors)
{
    //Stop currently playing
    Stop();

    // Configure Timer1 (Frequency)
    TCCR1A = 0; // Reset register
    TCCR1B = 0; // Reset register
    TCNT1  = 0; // Initialize counter value to 0
    TCCR1B |= _BV(WGM12); // Enable CTC mode

    //First check how many endpoints are needed
    uint8_t index = 0;
    for(auto d = descriptors.begin(); d < descriptors.end(); d++, index++)
    {
        if(d != nullptr)
        {
            endpoint_count++;
        }
    }


    // Configure streams
    OCR1A  = F_CPU / CAudio::FREQUENCY;
    TCCR1B |= _BV(CS10); // Set CS10 bit for 1 prescaler

    //Set up endpoints
    index = 0;
    for(auto d = descriptors.begin(); d < descriptors.end(); d++, index++)
    {
        if(d != nullptr)
        {
            endpoint[index].assign(d);
        }
    }
    
    EnableInterrupt();
}


void CAudio::Stop(void)
{
    DisableInterrupt();

    for (uint8_t index = 0; index < COUNT; index++)
    {
        endpoint[index].stop();
    }
}

__attribute__((optimize("unroll-loops", "-O3")))
void CAudio::InterruptMultipleStreams(void)
{
    static uint8_t count = 0;

    for (uint8_t index = 0; index < COUNT; index++)
    {
        endpoint[index].tick();
    }
    
    // Check if millisecond elapsed
    if (count++ >= (FREQUENCY / 1000))
    {
        count = 0; // Reset millisecond count

        for (uint8_t index = 0; index < COUNT; index++)
        {
            endpoint[index].tock();
        }
        
        // Disable interrupt if all endpoints stopped
        if (!IsActive())
        {
            DisableInterrupt();
        }
    }
}


ISR(TIMER1_COMPA_vect)
{
    (g_callback_object->InterruptMultipleStreams)();
}
