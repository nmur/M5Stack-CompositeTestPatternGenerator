# Setting up the Hardware

You will need to obtain a [M5StickC PLUS2 ESP32 controller](https://shop.m5stack.com/products/m5stickc-plus2-esp32-mini-iot-development-kit) from M5Stack directly, or one of their [distributors](https://m5stack.com/distributor).

Unfortunately the RCA adapter hat shown in the photos is not available from M5Stack, it's a small custom PCB housed in a [M5StickC Proto Hat](https://shop.m5stack.com/products/m5stickc-proto-hat), and requires the PCB to be printed as well as some DIY soldering.

You can still assemble compatible hardware with all off-the-shelf parts from M5Stack, it will just be less elegant than the aforementioned option.

## Custom DIY RCA PCB Hat
 
👍 Neatest and most compact option  
👎 Requires PCB to be printed and extra parts soldered

1. Print the PCB by uploading the [gerber zip file](https://github.com/nmur/M5Stack-CompositeTestPatternGenerator/raw/refs/heads/main/plot/Gerber_M5StickRcaHat_PCB_M5StickRcaHat.zip) to a service such as JLCPCB  
  a. Set the board thickness to 1mm
  b. (I haven't tested v0.2 of the PCB yet, will update this when I can)
3. Order the following extra parts  
  a. Yellow RCA jack ([Aliexpress](https://www.aliexpress.com/item/4000661815158.html?spm=a2g0o.order_list.order_list_main.5.2d491802O1wsq3))  
  b. 2.54mm 1x40P 90 Degree Right Angle Single Row Male Pin Header (reverse) ([Aliexpress](https://www.aliexpress.com/item/1005006795400618.html?spm=a2g0o.order_list.order_list_main.20.2d491802O1wsq3))  
  c. 75 Ohm resistor  
  d. 4.7 Ohm resistor  
  e. M5StickC Proto Hat ([M5Stack](https://shop.m5stack.com/products/m5stickc-proto-hat), [Aliexpress](https://www.aliexpress.com/item/1005003297314936.html))  
4. Disassemble the M5StickC Proto Hat and put the blank PCB aside
5. Solder the parts on the PCB, following the silkscreen text. Try to match the pin header positioning from the blank PCB in the Proto Hat
6. Reassemble the Proto Hat

<img width="473" height="406" alt="image" src="https://github.com/user-attachments/assets/22134a9a-933d-410b-a8bd-41a01e50a2a0" /> <img width="353" height="408" alt="image" src="https://github.com/user-attachments/assets/064eb660-67f7-47b6-97a3-2c4e87d25948" />

<img width="835" height="466" alt="image" src="https://github.com/user-attachments/assets/1073bbcd-961f-47bd-9db9-be20ddd13bc2" />


## Off-the-Shelf M5Stack Components
 
👍 No DIY required  
👎 Not as neat and tidy

Order the following extra parts from M5Stack:
1. [RCA Unit](https://shop.m5stack.com/products/rca-audio-video-composite-unit)
2. [Grove2Dupont Conversion Cable](https://shop.m5stack.com/products/grove2dupont-conversion-cable-20cm-5pairs)

Connect the components as follow:

| Header | Pin |
| :------ | :---------: |
| Black | GND |
| Red | 5V |
| Yellow | G26 |
| White | G36/G25 |

<img width="793" height="432" alt="image" src="https://github.com/user-attachments/assets/6c093d8e-ce4f-4245-ad60-72ccfc16c3c3" />

