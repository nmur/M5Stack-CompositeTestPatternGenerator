# Setting up the Hardware

You need an original ESP32-based M5StickC Plus-family controller and a
composite adapter connected to GPIO26. Consult the
[compatibility table](../README.md#device-compatibility) before purchasing a
controller: only M5StickC Plus v1 has been tested with this firmware revision.
Plus v1.1 and Plus2 hardware validation is pending, while Plus SE support is
currently experimental pending access to hardware.

The RCA adapter hat shown in the photos is not available from M5Stack. It is a
small custom PCB housed in an
[M5StickC Proto Hat](https://shop.m5stack.com/products/m5stickc-proto-hat), and
requires the PCB to be manufactured and assembled.

You can also assemble a compatible adapter from off-the-shelf M5Stack
components.

## Custom DIY RCA PCB Hat
 
👍 Neatest and most compact option  
👎 Requires PCB to be printed and extra parts soldered

1. Upload the
   [Gerber archive](../plot/Gerber_M5StickRcaHat_PCB_M5StickRcaHat.zip) to a PCB
   manufacturer. Set the board thickness to 1 mm.
2. Obtain these additional parts:
   - Yellow RCA jack ([AliExpress](https://www.aliexpress.com/item/4000661815158.html))
   - Reverse 2.54 mm, 1×40-pin, 90-degree male header ([AliExpress](https://www.aliexpress.com/item/1005006795400618.html))
   - 75 Ω resistor
   - 4.7 Ω resistor
   - M5StickC Proto Hat ([M5Stack](https://shop.m5stack.com/products/m5stickc-proto-hat), [AliExpress](https://www.aliexpress.com/item/1005003297314936.html))
3. Disassemble the M5StickC Proto Hat and put its blank PCB aside.
4. Solder the components by following the custom PCB's silkscreen. Match the
   pin-header position of the Proto Hat's original blank PCB.
   - Straightening the RCA jack pins with pliers can make installation easier.
   - Trim the soldered leads short enough to clear the housing base.
5. Reassemble the Proto Hat.

<img width="473" height="406" alt="image" src="https://github.com/user-attachments/assets/22134a9a-933d-410b-a8bd-41a01e50a2a0" /> <img width="353" height="408" alt="image" src="https://github.com/user-attachments/assets/064eb660-67f7-47b6-97a3-2c4e87d25948" />

## Off-the-Shelf M5Stack Components
 
👍 No DIY required  
👎 Not as neat and tidy

Order the following extra parts from M5Stack:

1. [RCA Unit](https://shop.m5stack.com/products/rca-audio-video-composite-unit)
2. [Grove2Dupont Conversion Cable](https://shop.m5stack.com/products/grove2dupont-conversion-cable-20cm-5pairs)

Connect the components as follows:

| Cable lead | Controller pin |
|---|---:|
| Black | GND |
| Red | 5V |
| Yellow | G26 |
| White | G36/G25 |

<img width="793" height="432" alt="image" src="https://github.com/user-attachments/assets/6c093d8e-ce4f-4245-ad60-72ccfc16c3c3" />
