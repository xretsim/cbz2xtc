#!/usr/bin/env python3
"""
cbz2xtc - Convert CBZ manga files to XTC format for XTEink X4
All-in-one tool: CBZ extraction → PNG optimization → XTC conversion

Usage:
    cbz2xtc                    # Process current directory
    cbz2xtc /path/to/folder    # Process specific folder
    cbz2xtc --clean            # Process and clean up intermediate files
    cbz2xtc --dither           # Apply dithering for better grayscale→B&W conversion
"""


import os
import sys
import zipfile
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

global GUIMODE
GUIMODE = "--gui" in sys.argv
if GUIMODE:
    import tkinter as tk  # Beginning of GUI work
    from PIL import ImageTk
    import platform

# Configuration
TARGET_WIDTH = 480
TARGET_HEIGHT = 800

# Global flag for dithering (default True)
USE_DITHERING = True



def find_png2xtc():
    """
    Find png2xtc.py in common locations
    Returns path if found, None otherwise
    """
    possible_paths = [
        # Check environment variable first
        Path(os.environ.get('PNG2XTC_PATH', '')),
        # Same directory as this script
        Path(__file__).parent / "png2xtc.py",
        # epub2xtc subfolder
        Path(__file__).parent / "epub2xtc" / "png2xtc.py",
        # Parent directory
        Path(__file__).parent.parent / "png2xtc.py",
        # Parent epub2xtc folder
        Path(__file__).parent.parent / "epub2xtc" / "png2xtc.py",
        # Windows common location
        Path(r"H:\commandline_tools\epub2xtc\png2xtc.py"),
        # Linux/Mac common locations
        Path.home() / ".local" / "bin" / "png2xtc.py",
        Path("/usr/local/bin/png2xtc.py"),
    ]
    
    for path in possible_paths:
        if path.exists():
            # print("png2xtc exists at ",path) # debugging.
            return path
    
    return None

def gui_preview_image(img_data, output_path_base, page_num):
    boxsize = GUI_PREVIEW_SIZE
    try:
        a=Path(output_path_base.parent / f"{page_num:04d}_preview_{boxsize}.png")
        if not a.exists():
            from io import BytesIO
            uncropped_img = Image.open(BytesIO(img_data))
            output_page = output_path_base.parent / f"{page_num:04d}_preview_{boxsize}.png"
            save_gui_thumbs(uncropped_img, output_page, boxsize=boxsize)
    except Exception as e:
        print(f"    Warning: Could not optimize image: {e}")
        return 0

def contrast_boost_image(input_img, need_boost=False, contrast_values=None, page_num="0"):
    if not need_boost:
        need_boost = CONTRAST_BOOST
    if not contrast_values:
        contrast_values = CONTRAST_VALUE
    contrast_black = 0
    contrast_white = 0
    if contrast_values and len(contrast_values.split(',')) > 1:
        contrast_black = int(contrast_values.split(',')[0])
        contrast_white = int(contrast_values.split(',')[1])
    elif contrast_values:
        contrast_black = int(contrast_values)
        contrast_white = int(contrast_values)
    else:
        contrast_black = 0
        contrast_white = 0
    if SPECIAL_CONTRASTS and page_num in SPECIAL_CONTRAST_PAGES:
        need_boost = True
        special_contrast_pos = SPECIAL_CONTRAST_PAGES.index(page_num)
        contrast_black = SPECIAL_CONTRAST_DARKS[special_contrast_pos]
        contrast_white = SPECIAL_CONTRAST_LIGHTS[special_contrast_pos]
    #enhance contrast
    output_img = None
    if need_boost:
        # print("contrast settings:", contrast_black, contrast_white, "page:", page_num)
        if contrast_black == 0 and contrast_white == 0:
            pass  # we don't need to adjust contrast at all.
        elif contrast_black != contrast_white:
            #passed a list of 2, first is dark cutoff, second is bright cutoff.
            black_cutoff = 3 * contrast_black
            white_cutoff = 3 + 9 * contrast_white
            output_img = ImageOps.autocontrast(input_img, cutoff=(black_cutoff,white_cutoff), preserve_tone=True)
        elif int(contrast_black) < 0 or int(contrast_black) > 8:
            pass # value out of range. we'll treat like 0.
        else:
            black_cutoff = 3 * contrast_black
            white_cutoff = 3 + 9 * contrast_white
            output_img = ImageOps.autocontrast(input_img, cutoff=(black_cutoff,white_cutoff), preserve_tone=True)
    else:
        # nothing set, so we go with the default value of 4. 
        black_cutoff = 3 * 4    # default, contrast level 4 = 12
        white_cutoff = 3 + 9 * 4    # default, contrast level 4 = 39
        output_img = ImageOps.autocontrast(input_img, cutoff=(black_cutoff,white_cutoff), preserve_tone=True)
        # uncropped_img = ImageOps.autocontrast(uncropped_img, cutoff=(8,35), preserve_tone=True)
    if output_img:
        return output_img
    else:
        return input_img

def optimize_image(img_data, output_path_base, page_num, suffix=""):
    """
    Optimize image for XTEink X4:
    - crop off image margins (if active)
    - Increase image contrast (unless disabled)
    - Split image in half or overlapping thirds horizontally
    - Rotate each half 90° clockwise
    - Resize to fit 480x800 with white padding
    - Convert to grayscale
    - Save as PNG (for XTC conversion)
    """
    try:
        from io import BytesIO
        uncropped_img = Image.open(BytesIO(img_data))

        if IS_MANGA:
            if suffix == "_1":
                #right half of a spread first because manga
                width, height = uncropped_img.size
                uncropped_img = uncropped_img.crop((int(50/100.0*width), int(0/100.0*height), width-int(0/100.0*width), height-int(0/100.0*height)))
            if suffix == "_2":
                #left half of a spread next because manga
                width, height = uncropped_img.size
                uncropped_img = uncropped_img.crop((int(0/100.0*width), int(0/100.0*height), width-int(50/100.0*width), height-int(0/100.0*height)))
        else:
            if suffix == "_1":
                #left half of a spread
                width, height = uncropped_img.size
                uncropped_img = uncropped_img.crop((int(0/100.0*width), int(0/100.0*height), width-int(50/100.0*width), height-int(0/100.0*height)))
            if suffix == "_2":
                #right half of a spread
                width, height = uncropped_img.size
                uncropped_img = uncropped_img.crop((int(50/100.0*width), int(0/100.0*height), width-int(0/100.0*width), height-int(0/100.0*height)))

        if SKIP_ON:
            if str(page_num) in SKIP_PAGES: 
                print("skipping page:",page_num)
                return 0

        if START_PAGE and page_num < START_PAGE:
            # we haven't reached the start page yet
            return 0

        if STOP_PAGE and page_num > STOP_PAGE:
            # we've passed the stop page.
            return 0

        if ONLY_ON:
            if str(page_num) not in ONLY_PAGES: 
                return 0

        if SAMPLE_SET:
            if str(page_num) in SAMPLE_PAGES:
                if uncropped_img.mode != 'L':
                    uncropped_img = uncropped_img.convert('L')
                font = ImageFont.load_default(size=100)
                text_color = 0
                box_color = 255
                print("creating samples for page:",page_num)
                width, height = uncropped_img.size
                text_position = (width//8,height//2)
                # box_position = [(width//8)-10, (height//2)-10, (width//8)+200, (height//2)+40]
                box_position = ((width//8)-30, (height//2), (width//8)+496, (height//2)+120)
                width_proportion = width / 800
                overlapping_third_height = 480 * width_proportion // 1
                shiftdown_to_overlap = overlapping_third_height - (overlapping_third_height * 3 - height) // 2
                contrast_set = 0
                while contrast_set < 9:
                    black_cutoff = 3 * contrast_set
                    white_cutoff = 3 + 9 * contrast_set
                    page_view = ImageOps.autocontrast(uncropped_img, cutoff=(black_cutoff,white_cutoff), preserve_tone=True)
                    draw = ImageDraw.Draw(page_view)
                    draw.rounded_rectangle(box_position, radius=60, fill=box_color, outline=text_color, width=6, corners=(False,True,False,True))
                    draw.text(text_position, f"Contrast {contrast_set}", fill=text_color, font=font)
                    output_page = output_path_base.parent / f"{page_num:04d}_0_contrast{contrast_set}.png"
                    save_with_padding(page_view, output_page, padcolor=PADDING_COLOR)
                    middle_third = page_view.crop((0, shiftdown_to_overlap, width, height - shiftdown_to_overlap))
                    middle_rotated = middle_third.rotate(-90, expand=True)
                    output_middle = output_path_base.parent / f"{page_num:04d}_3_b_contrast{contrast_set}.png"
                    save_with_padding(middle_rotated, output_middle, padcolor=PADDING_COLOR)
                    contrast_set += 1
                crop_set = 0.0
                contrast3img = ImageOps.autocontrast(uncropped_img, cutoff=(9,30), preserve_tone=True)
                while crop_set < 10:
                    allaroundcrop = crop_set
                    page_view = contrast3img.crop((int(allaroundcrop/100.0*width), int(allaroundcrop/100.0*height), width-int(allaroundcrop/100.0*width), height-int(allaroundcrop/100.0*height)))
                    draw = ImageDraw.Draw(page_view)
                    draw.rounded_rectangle(box_position, radius=60, fill=box_color, outline=text_color, width=6, corners=(False,True,False,True))
                    draw.text(text_position, f"Margin {crop_set}", fill=text_color, font=font)
                    output_page = output_path_base.parent / f"{page_num:04d}_9_margin{crop_set}.png"
                    save_with_padding(page_view, output_page, padcolor=30)                    
                    crop_set += 0.5
            else:
                pass
                # print("skipping page:",page_num)
            return 0

        uncropped_img = contrast_boost_image(uncropped_img, page_num = page_num)

        # Convert to grayscale
        if uncropped_img.mode != 'L':
            uncropped_img = uncropped_img.convert('L')
        
        img = uncropped_img
        width, height = img.size

        #crop margins in percentage. 
        if MARGIN or suffix:
            if MARGIN_VALUE == "0":
                pass #we don't need to do margins at all.
            elif MARGIN_VALUE.lower() == "auto" or suffix:
                # trim white space from all four sides.  # This is always used for split-spreads, since other margins unreliable. 
                invert_img=ImageOps.invert(uncropped_img) #invert image
                invert_img=ImageOps.autocontrast(invert_img,cutoff=(59,40))
                image_box_coords = invert_img.getbbox() # bounding rect around anything not true black.
                img = uncropped_img.crop(image_box_coords)
            elif len(MARGIN_VALUE.split(',')) > 1:
                marginlist = MARGIN_VALUE.split(',')
                marginlist.append("0")
                marginlist.append("0") # 2 0s just in case there aren't four values.
                leftcrop = float(marginlist[0])
                topcrop = float(marginlist[1])
                rightcrop = float(marginlist[2])
                bottomcrop = float(marginlist[3])
                img = uncropped_img.crop((int(leftcrop/100.0*width), int(topcrop/100.0*height), width-int(rightcrop/100.0*width), height-int(bottomcrop/100.0*height)))
            else:
                allaroundcrop = float(MARGIN_VALUE);
                img = uncropped_img.crop((int(allaroundcrop/100.0*width), int(allaroundcrop/100.0*height), width-int(allaroundcrop/100.0*width), height-int(allaroundcrop/100.0*height)))

        width, height = img.size
        half_height = height // 2
        total_size = 0

        should_this_split = width < height  #we split most pages that are vertical.
        if str(page_num) in SPLIT_SPREADS_PAGES:
            if suffix == "":  
                # we haven't recursed, this is top level.
                should_this_split = False  #we're not splitting this vertically, we're halving it, then the halves will be split recursively.
            else:
                # we have recursed.
                should_this_split = True  #we can't recurse again, it's been halved, it must be split.
        if SPLIT_ALL:  
            #well, that's easy, we split!
            should_this_split = True
        if suffix == "" and str(page_num) in DONT_SPLIT_PAGES:  
            #also easy, we don't split. Overrides everything. (excepting recursion)
            should_this_split = False

        if should_this_split:
            thumbnail_scale = 1.0*THUMBNAIL_WIDTH/width
            thumbnail_height = int(thumbnail_scale*height)
            img_thumbnail = 0
            if THUMBNAIL_WIDTH > 0:
                img_thumbnail = img.resize((THUMBNAIL_WIDTH,thumbnail_height), Image.Resampling.LANCZOS).rotate(-90, expand=True).convert("LA")
                draw = ImageDraw.Draw(img_thumbnail)
                draw.rectangle((0,0,thumbnail_height,THUMBNAIL_WIDTH), outline=PADDING_COLOR, width=5)

            if INCLUDE_OVERVIEWS or SIDEWAYS_OVERVIEWS or SELECT_OVERVIEWS:
                if SELECT_OVERVIEWS and (str(page_num) not in SELECT_OV_PAGES):
                    pass
                    # we're only doing overviews for some pages, and this one isn't one.
                else:
                    # Process overview page
                    page_view = uncropped_img;
                    if not SIDEWAYS_OVERVIEWS:
                        page_view = uncropped_img.rotate(-90, expand=True)
                    output_page = output_path_base.parent / f"{page_num:04d}{suffix}_0_overview.png"
                    save_with_padding(page_view, output_page, padcolor=PADDING_COLOR)

            if OVERLAP or DESIRED_V_OVERLAP_SEGMENTS or SET_H_OVERLAP_SEGMENTS or page_num in SPECIAL_SPLITS_PAGES:
                # DESIRED_V_OVERLAP_SEGMENTS = 3
                # SET_H_OVERLAP_SEGMENTS = 1
                # MINIMUM_V_OVERLAP_PERCENT = 5
                # SET_H_OVERLAP_PERCENT = 75
                # MAX_SPLIT_WIDTH = 80

                number_of_h_segments = SET_H_OVERLAP_SEGMENTS
                h_overlap_percent = SET_H_OVERLAP_PERCENT
                if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    number_of_h_segments = SPECIAL_SPLIT_HSPLITS[special_split_pos]
                    h_overlap_percent = SPECIAL_SPLIT_HOVERLAP[special_split_pos]
                total_calculated_width = MAX_SPLIT_WIDTH * number_of_h_segments - int((number_of_h_segments - 1) * (MAX_SPLIT_WIDTH * 0.01 * h_overlap_percent))
                    # so, 1 = 800. 2 with 33% overlap = 1334, 3 with 33% overlap = 1868px, etc.
                established_scale = total_calculated_width * 1.0 / width
                    # so for 2000px wide source, 1= 0.4, 2=0.667, etc. 

                overlapping_width = MAX_SPLIT_WIDTH / established_scale // 1
                shiftover_to_overlap = 0
                if number_of_h_segments > 1:
                    shiftover_to_overlap = overlapping_width - (overlapping_width * number_of_h_segments - width) // (number_of_h_segments - 1)

                number_of_v_segments = DESIRED_V_OVERLAP_SEGMENTS - 1
                minimum_v_overlap = MINIMUM_V_OVERLAP_PERCENT
                if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    number_of_v_segments = SPECIAL_SPLIT_VSPLITS[special_split_pos]-1
                    minimum_v_overlap = -100
                letter_keys = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z"]
                letter_keys_hsplit = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z"]
                if IS_MANGA:
                    letter_keys_hsplit.reverse()

                # width_proportion = width / 800
                overlapping_height = 480 / established_scale // 1
                shiftdown_to_overlap = 99999
                while number_of_v_segments < 26 and (shiftdown_to_overlap * 1.0 / overlapping_height) > (1.0 - .01 * minimum_v_overlap):
                    # iterate until we have a number of segments that cover the page with sufficient overlap.
                    # the first iteration should fix the 99999 thing and set up our "base" attempt.
                    number_of_v_segments += 1
                    shiftdown_to_overlap = 0
                    if number_of_v_segments > 1:
                        shiftdown_to_overlap = overlapping_height - (overlapping_height * number_of_v_segments - height) // (number_of_v_segments - 1)

                # # debugging math output
                # print (f"width:{width}, height:{height}")
                # print (f"overlapping_width:{overlapping_width}, overlapping_height:{overlapping_height}")
                # print (f"shiftdown_to_overlap:{shiftdown_to_overlap}, shiftover_to_overlap:{shiftover_to_overlap}")
                # print (f"established_scale:{established_scale}")

                # Make overlapping segments that fill 800x480 screen.
                v = 0
                use_segment_list = []
                if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    use_segment_list = SPECIAL_SPLIT_BOOLEANS[special_split_pos]
                    print("special split for page:",SPECIAL_SPLIT_PAGES[special_split_pos]," segment list:",use_segment_list)
                while v < number_of_v_segments:
                    h = 0
                    while h < number_of_h_segments:
                        segment = img.crop((shiftover_to_overlap*h, shiftdown_to_overlap*v, width-(shiftover_to_overlap*(number_of_h_segments-h-1)), height-(shiftdown_to_overlap*(number_of_v_segments-v-1))))
                        segment_rotated = segment.rotate(-90, expand=True)
                        if number_of_h_segments > 1:
                            output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}_{letter_keys_hsplit[h]}.png"
                        else:
                            output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}.png"
                        if THUMBNAIL_WIDTH > 0:
                            if THUMBNAIL_HIGHLIGHT_ACTIVE:
                                highlight_opacity = 96
                                thumbnail_overlay = Image.new('LA', img_thumbnail.size)
                                draw_thumb_overlay = ImageDraw.Draw(thumbnail_overlay)
                                thumb_region_right = int(thumbnail_height - shiftdown_to_overlap*v*thumbnail_scale)
                                thumb_region_top = int(shiftover_to_overlap*h*thumbnail_scale)
                                thumb_region_left = int(thumbnail_height - shiftdown_to_overlap*v*thumbnail_scale - overlapping_height*thumbnail_scale)
                                thumb_region_bottom = int(THUMBNAIL_WIDTH-(shiftover_to_overlap*(number_of_h_segments-h-1))*thumbnail_scale)
                                draw_thumb_overlay.rectangle((thumb_region_left,thumb_region_top,thumb_region_right,thumb_region_bottom), fill=(255,highlight_opacity), outline=(PADDING_COLOR,255), width=3)
                                img_temp_thumbnail = Image.alpha_composite(img_thumbnail, thumbnail_overlay).convert("L")
                                if len(use_segment_list)==0 or use_segment_list[0]=="1":
                                    size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR, thumbnail=img_temp_thumbnail)    
                            else:
                                if len(use_segment_list)==0 or use_segment_list[0]=="1":
                                    size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR, thumbnail=img_thumbnail)
                        else:
                            if len(use_segment_list)==0 or use_segment_list[0]=="1":
                                size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR)
                        if len(use_segment_list)>0:
                            use_segment_list.pop(0)
                        h += 1
                    v += 1

                # v = 0
                # while v < number_of_v_segments:
                #     h = 0
                #     while h < number_of_h_segments:
                #         segment = img.crop((shiftover_to_overlap*h, shiftdown_to_overlap*v, width-(shiftover_to_overlap*(number_of_h_segments-h-1)), height-(shiftdown_to_overlap*(number_of_v_segments-v-1))))
                #         segment_rotated = segment.rotate(-90, expand=True)
                #         if number_of_h_segments > 1:
                #             output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}_{letter_keys[h]}.png"
                #         else:
                #             output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}.png"
                #         size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR, thumbnail=img_thumbnail)
                #         h += 1
                #     v += 1


                # # Make overlapping vertical column of full-width segments that fill screen.
                # i = 0
                # while i < number_of_segments:
                #     segment = img.crop((0,shiftdown_to_overlap*i, width, height-(shiftdown_to_overlap*(number_of_segments-i-1))))
                #     segment_rotated = segment.rotate(-90, expand=True)
                #     output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[i]}.png"
                #     size = save_with_padding(segment_rotated, output)
                #     i += 1

                # # Process top third
                # top_third = img.crop((0, 0, width, overlapping_third_height))
                # top_rotated = top_third.rotate(-90, expand=True)
                # output_top = output_path_base.parent / f"{page_num:04d}{suffix}_3_a.png"
                # size = save_with_padding(top_rotated, output_top)
                # total_size += size;

                # # Process middle third
                # middle_third = img.crop((0, shiftdown_to_overlap, width, height - shiftdown_to_overlap))
                # middle_rotated = middle_third.rotate(-90, expand=True)
                # output_middle = output_path_base.parent / f"{page_num:04d}{suffix}_3_b.png"
                # size = save_with_padding(middle_rotated, output_middle)
                # total_size += size;

                # # Process middle third
                # bottom_third = img.crop((0, shiftdown_to_overlap*2, width, height))
                # bottom_rotated = bottom_third.rotate(-90, expand=True)
                # output_bottom = output_path_base.parent / f"{page_num:04d}{suffix}_3_c.png"
                # size = save_with_padding(bottom_rotated, output_bottom)
                # total_size += size;

            else:
                # Process top half
                top_half = img.crop((0, 0, width, half_height))
                top_rotated = top_half.rotate(-90, expand=True)
                output_top = output_path_base.parent / f"{page_num:04d}{suffix}_2_a.png"
                if THUMBNAIL_WIDTH > 0:
                    if THUMBNAIL_HIGHLIGHT_ACTIVE:
                        highlight_opacity = 96
                        thumbnail_overlay = Image.new('LA', img_thumbnail.size)
                        draw_thumb_overlay = ImageDraw.Draw(thumbnail_overlay)
                        draw_thumb_overlay.rectangle((thumbnail_height//2,0,thumbnail_height,THUMBNAIL_WIDTH), fill=(255,highlight_opacity), outline=(PADDING_COLOR,255), width=3)
                        img_temp_thumbnail = Image.alpha_composite(img_thumbnail, thumbnail_overlay).convert("L")
                        size = save_with_padding(top_rotated, output_top, padcolor=PADDING_COLOR, thumbnail=img_temp_thumbnail)
                    else:
                        size = save_with_padding(top_rotated, output_top, padcolor=PADDING_COLOR, thumbnail=img_thumbnail)
                else:
                    size = save_with_padding(top_rotated, output_top, padcolor=PADDING_COLOR)
                total_size += size
                
                # Process bottom half
                bottom_half = img.crop((0, half_height, width, height))
                bottom_rotated = bottom_half.rotate(-90, expand=True)
                output_bottom = output_path_base.parent / f"{page_num:04d}{suffix}_2_b.png"
                if THUMBNAIL_WIDTH > 0:
                    if THUMBNAIL_HIGHLIGHT_ACTIVE:
                        highlight_opacity = 96
                        thumbnail_overlay = Image.new('LA', img_thumbnail.size)
                        draw_thumb_overlay = ImageDraw.Draw(thumbnail_overlay)
                        draw_thumb_overlay.rectangle((0,0,thumbnail_height//2,THUMBNAIL_WIDTH), fill=(255,highlight_opacity), outline=(PADDING_COLOR,255), width=3)
                        img_temp_thumbnail = Image.alpha_composite(img_thumbnail, thumbnail_overlay).convert("L")
                        size = save_with_padding(bottom_rotated, output_bottom, padcolor=PADDING_COLOR, thumbnail=img_temp_thumbnail)
                    else:
                        size = save_with_padding(bottom_rotated, output_bottom, padcolor=PADDING_COLOR, thumbnail=img_thumbnail)
                else:
                    size = save_with_padding(bottom_rotated, output_bottom, padcolor=PADDING_COLOR)
                total_size += size
        
        elif width >= height or str(page_num) in SPLIT_SPREADS_PAGES:
            # Process wide page, or specifically split narrow page (rare, but for two-column layouts)
            # top_half = img.crop((0, 0, width, half_height))
            page_rotated = img.rotate(-90, expand=True)
            output_page = output_path_base.parent / f"{page_num:04d}{suffix}_0_spread.png"
            size = save_with_padding(page_rotated, output_page, padcolor=PADDING_COLOR)
            if SPLIT_SPREADS and (SPLIT_SPREADS_PAGES[0] == "all" or str(page_num) in SPLIT_SPREADS_PAGES):
                splitLeft = optimize_image(img_data, output_path_base, page_num, suffix=suffix+"_1")
                splitRight = optimize_image(img_data, output_path_base, page_num, suffix=suffix+"_2")
            total_size += size
        else: 
            # This is a dont-split page, treat like overview page
            page_view = uncropped_img;
            if not SIDEWAYS_OVERVIEWS:
                page_view = uncropped_img.rotate(-90, expand=True)
            output_page = output_path_base.parent / f"{page_num:04d}{suffix}_0_overview.png"
            save_with_padding(page_view, output_page, padcolor=PADDING_COLOR)

        return total_size
        
    except Exception as e:
        print(f"    Warning: Could not optimize image: {e}")
        return 0

def save_with_padding(img, output_path, *, padcolor=255, thumbnail=False):
    """
    Resize image to fit within 480x800 and add white padding
    Optionally apply dithering for better B&W conversion
    """
    img_width, img_height = img.size
    scale = min(TARGET_WIDTH / img_width, TARGET_HEIGHT / img_height)
    
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Apply dithering if enabled (for better grayscale → B&W conversion)
    if USE_DITHERING:
        # Convert to 1-bit with Floyd-Steinberg dithering
        img_resized = img_resized.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
        # Convert back to grayscale mode so we can paste on white background
        img_resized = img_resized.convert('L')
    
    # Create background (default padcolor is white)
    result = Image.new('L', (TARGET_WIDTH, TARGET_HEIGHT), color=padcolor)
    
    # Center the image
    x = (TARGET_WIDTH - new_width) // 2
    y = (TARGET_HEIGHT - new_height) // 2
    
    if thumbnail:
        # Move image to the right
        y = (TARGET_HEIGHT - new_height)

    result.paste(img_resized, (x, y))

    if thumbnail:
        # thumb_width, thumb_height = thumbnail.size
        # thumb_x = 0
        if USE_DITHERING:
            # Convert to 1-bit with Floyd-Steinberg dithering
            thumbnail = thumbnail.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
            # Convert back to grayscale mode so we can paste on white background
            thumbnail = thumbnail.convert('L')
        result.paste(thumbnail, (0,0))

    result.save(output_path, 'PNG', optimize=True)
    
    return output_path.stat().st_size

def save_gui_thumbs(img, output_path, boxsize=400):
    """
    Resize image to fit within 400x400
    """
    img_width, img_height = img.size
    scale = min(boxsize / img_width, boxsize / img_height)
    
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    img_resized.save(output_path, 'PNG', optimize=True)

    return output_path.stat().st_size

def extract_cbz_to_png(cbz_path, temp_dir, gui_thumbnails=False):
    """
    Extract CBZ and convert to optimized PNGs
    Returns the folder path with PNGs or None if failed
    """
    cbz_name = cbz_path.stem
    output_folder = temp_dir / cbz_name
    output_folder.mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
            os_metadata_exclusions = ('__macos') # .cbzs made on Macs sometimes have mac-specific metadata in a __macos directory.
            image_files = [f for f in file_list if f.lower().endswith(image_extensions) and not f.lower().startswith(os_metadata_exclusions)]
            image_files.sort()

            if not image_files:
                print(f"  ✗ No images found in {cbz_name}")
                return None
            
            print(f"  Extracting {len(image_files)} pages...", end=" ", flush=True)
            
            for idx, img_file in enumerate(image_files, 1):
                img_data = zip_ref.read(img_file)
                output_base = output_folder / f"{idx:04d}"
                if gui_thumbnails:
                    gui_preview_image(img_data, output_base, idx)
                else:
                    optimize_image(img_data, output_base, idx)
            
            print(f"✓")
            return output_folder
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None


def convert_png_folder_to_xtc(png_folder, output_file):
    """
    Convert folder of PNGs to XTC using png2xtc.py
    """
    png2xtc_path = find_png2xtc()
    
    if not png2xtc_path:
        print(f"  ✗ Error: png2xtc.py not found")
        print(f"     Please install epub2xtc or set PNG2XTC_PATH environment variable")
        return False
    
    try:
        # print("trying path:",str(png2xtc_path))
        result = subprocess.run(
            # ["python", str(png2xtc_path), str(png_folder), str(output_file)],
            # I had to use the following instead to make this work on my Mac.
            ["python3", str(png2xtc_path) + "/png2xtc.py", str(png_folder), str(output_file)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0 and output_file.exists():
            size_mb = output_file.stat().st_size / 1024 / 1024
            print(f"  ✓ Created {output_file.name} ({size_mb:.1f}MB)")
            return True
        else:
            print(f"  ✗ Conversion failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Conversion timed out")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def process_cbz_file(cbz_path, output_dir, temp_dir, clean_temp, file_num=None, total_files=None):
    """
    Full pipeline: CBZ → PNG → XTC
    """
    progress_prefix = f"[{file_num}/{total_files}] " if file_num and total_files else ""
    print(f"\n{progress_prefix}Processing: {cbz_path.name}")
    
    start_time = time.time()
    
    # Step 1: Extract and optimize to PNG
    png_folder = extract_cbz_to_png(cbz_path, temp_dir)
    if not png_folder:
        return False, cbz_path.name, 0
    
    # Step 2: Convert to XTC
    output_file = output_dir / f"{cbz_path.stem}.xtc"
    success = convert_png_folder_to_xtc(png_folder, output_file)
    
    # Step 3: Clean up temp files if requested
    if clean_temp and png_folder.exists():
        shutil.rmtree(png_folder)
    
    elapsed = time.time() - start_time
    return success, cbz_path.name, elapsed


def main():
    print("=" * 60)
    print("CBZ to XTC Converter for XTEink X4")
    print("=" * 60)
    
    # Check for help flag
    if "--help" in sys.argv or "-h" in sys.argv:
        print("\nConverts CBZ manga files to XTC format optimized for XTEink X4")
        print("\nUsage:")
        print("  cbz2xtc                           # Process current directory")
        print("  cbz2xtc /path/to/folder           # Process specific folder")
        print("  cbz2xtc --no-dither               # Disable dithering")
        print("  cbz2xtc --clean                   # Auto-delete temp PNG files")
        print("  cbz2xtc --no-dither --clean       # Combine options")
        print("\nOptions:")
        print("  --no-dither   Disable Floyd-Steinberg dithering. By default,")
        print("                dithering is ENABLED for better grayscale to")
        print("                black & white conversion. Use this flag for pure")
        print("                threshold conversion (sharper for clean line art).")
        print("\n  --overlap     Split into 3 overlapping screen-filling pieces instead")
        print("                of 2 non-overlapping pieces that may leave margins.")
        print("\n  --thumbnail <#>   Creates a thumbnail that is # pixels wide on the left")
        print("                side. If using --overlap, combine with --hsplit-max-width")
        print("\n  --no-thumb-highlight   Do not highlight the position of the currently")
        print("                active split portion on the thumbnail (if present).")
        print("\n  --split-spreads all or <pagenum> or <pagenum,pagenum,pagenum...>")
        print("                Splits wide pages in half, and then split each of the")
        print("                halves as if they were normal pages. Useful if the")
        print("                wide pages are double-page spreads with text.")
        print("\n  --split-all   Splits ALL pages into pieces, even if those pages")
        print("                are wider than they are tall.")
        print("\n  --skip <pagenum> or <pagenum,pagenum,pagenum...>   skips page")
        print("                or pages entirely.")
        print("\n  --only <pagenum> or <pagenum,pagenum,pagenum...>   only renders")
        print("                the selected page or pages. Tip: If you don't use")
        print("                --clean, this can be used to rerender a problematic")
        print("                page or pages with different settings than the rest.")
        print("\n  --dont-split <pagenum> or <pagenum,pagenum,pagenum...>   don't split")
        print("                page or pages, will use an overview instead (vertical if")
        print("                --sideways-overviews is unset.) For covers and splash pages.")
        print("\n  --contrast-boost <0-8> or <#,#>   Enhances contrast by clipping off,")
        print("                brightest and darkest parts of the image. 0=no boost,")
        print("                4=strong (default), 6=very strong, 8=insane. If you")
        print("                specify two values with a comma, the first will be used")
        print("                for dark parts, and the second for light parts.")
        print("                in general, text will be more readable by increasing")
        print("                dark contrast, and images will gain clarity by")
        print("                increasing light contrast.")
        print("\n  --margin auto or <float> or <left,top,right,bottom>   crops off")
        print("                page margins by a percentage of the width or height.")
        print("                Use a single number to crop from all sides equally, or")
        print("                specify the cropping for each side in LTRB order.")
        print("                '--margin auto' trims white space from all 4 sides.")
        print("                (margin crop is not applied to overview pages.)")
        print("\n  --include-overviews   Show an overview of each page before the")
        print("                split pieces.")
        print("\n  --sideways-overviews   Show a rotated overview of each page before")
        print("                the split pieces. (better quality, but will require)")
        print("                reader to turn their device sideways)")
        print("\n  --select-overviews <pagenum> or <pagenum,pagenum,pagenum...>  Add")
        print("                overview pages for only the specified pages instead of")
        print("                for all pages. Will use vertical overviews if")
        print("                --sideways-overviews is unset. (--dont-split's listed")
        print("                pagenums will still automatically get overviews and")
        print("                don't need to be listed here again.)")
        print("\n  --start <pagenum>   Don't process pages before this page.")
        print("\n  --stop <pagenum>    Don't process pages after this page.")
        print("\n  --pad-black   Pad things that don't fill screen with black instead")
        print("\n  --hsplit-count <#>   Split page horizontally into # segments.")
        print("\n  --hsplit-overlap <float>   horizontal overlap between segments in")
        print("                percent. Default is 70 percent. Lowering this value will")  
        print("                almost always result in automatically splitting the page")  
        print("                vertically into more than 3 segments.")
        print("\n  --hsplit-max-width <#>   limit the width of horizontal segments")
        print("                to less than full screen. (allows for lower amounts of")
        print("                overlap without requiring extra vertical segmentation.)")
        print("\n  --vsplit-target <#>   try to split page vertically into # segments.")
        print("                if this would result it missing data or insufficient")
        print("                overlap of segments, it will automatically add more.")           
        print("\n  --vsplit-min-overlap <float>   minimum vertical overlap between segments.")
        print("                in percent. Default is 5 percent.")  
        print("\n  --manga       Horizontal splits and --split-spreads will be ordered")
        print("                right-to-left instead of left-to-right in the output.")  
        print("\n  --sample-set <pagenum> or <pagenum,pagenum,pagenum...>  Build a")
        print("                spread of contrast and margin samples for a page or")
        print("                list of pages. Useful for evaluating what settings")
        print("                you want to use. Does contrasts 0-8, margin 0-10 percent")
        print("\n  --special-split <specifier> or <specifier,specifier,specifier...> ")
        print("                (Advanced) specifier = pagenum-hsplit-vsplit-booleans-hoverlap,")
        print("                where hoverlap is horizontal overlap to use, and")
        print("                booleans is a list of 1 and 0s representing whether each")
        print("                segment is included in output or not. Ex: 121-2-4-01010111-50")
        print("                Booleans and hoverlap are optional.")
        print("\n  --special-contrast <specifier> or <specifier,specifier,specifier...> ")
        print("                (Advanced) specifier = pagenum-darkcontrast-lightcontrast,")
        print("                indicating alternate contrast settings for each specified")
        print("                page. Ex: 121-5-2")
        print("\n  --clean      Automatically delete temporary PNG files after")
        print("                conversion. Saves disk space and prevents leftover")
        print("                files from interfering with conversions using different")
        print("                split or overview settings.")
        print("\n  --help, -h    Show this help message")
        print("\nWhat it does:")
        print("  1. Extracts images from CBZ files")
        print("  2. Splits each page in half and rotates 90°")
        print("  3. Resizes to 480×800 with white padding")
        print("  4. Converts to grayscale PNG (with dithering by default)")
        print("  5. Converts PNG to XTC format (fast loading!)")
        print("  6. Uses multithreading (up to 4 parallel conversions)")
        print("\nOutput:")
        print("  - XTC files saved to: ./xtc_output/")
        print("  - Temp PNGs saved to: ./.temp_png/ (unless --clean)")
        print("\nExamples:")
        print("  cbz2xtc                           # Basic conversion (with dithering)")
        print("  cbz2xtc --clean                   # With cleanup")
        print("  cbz2xtc --no-dither               # Without dithering")
        print("  cbz2xtc --contrast 3,5 --margin 5,3.5,5,3.5 --split-spreads all")
        print("                     # good trial settings for a mainstream comic.")
        print("  cbz2xtc --dont-split 1            # show cover as single image")
        print("  cbz2xtc --sideways-overviews --dont-split 17 --select-overviews 19,24")
        print("                     # A sideways overview will be used instead of splits")
        print("                     # for page 17, and a sideways overview will come")
        print("                     # before the splits for pages 19 and 24.")
        print("  cbz2xtc --overlap --vsplit-target 7 --thumbnail 120 --hsplit-max-width 700")
        print("                     # Break up the page so it scrolls a little with")
        print("                     # each advance, showing the currently viewed segment")
        print("                     # as a highlight on a small thumbnail.")
        print("  cbz2xtc --overlap --hsplit-count 2 --hsplit-overlap 25 --hsplit-max-width 600")
        print("                     # split the page horizontally as well as vertically,")
        print("                     # with a slight overlap, only using 600px screen width on")
        print("                     # target device for the segmented pieces.")
        print("  cbz2xtc D:\\manga --clean          # Specific folder + cleanup")
        return 0
    
    # Parse arguments
    global USE_DITHERING
    global OVERLAP
    global THUMBNAIL_WIDTH
    global THUMBNAIL_HIGHLIGHT_ACTIVE
    global SPLIT_SPREADS
    global SPLIT_SPREADS_PAGES
    global SPLIT_ALL
    global SKIP_ON
    global SKIP_PAGES
    global ONLY_ON
    global ONLY_PAGES
    global DONT_SPLIT
    global DONT_SPLIT_PAGES
    global CONTRAST_BOOST
    global CONTRAST_VALUE
    global MARGIN
    global MARGIN_VALUE
    global INCLUDE_OVERVIEWS
    global SIDEWAYS_OVERVIEWS
    global SELECT_OVERVIEWS
    global SELECT_OV_PAGES
    global START_PAGE
    global STOP_PAGE
    global DESIRED_V_OVERLAP_SEGMENTS
    global SET_H_OVERLAP_SEGMENTS
    global MINIMUM_V_OVERLAP_PERCENT
    global SET_H_OVERLAP_PERCENT
    global MAX_SPLIT_WIDTH
    global IS_MANGA
    global SAMPLE_SET
    global SAMPLE_PAGES
    global SPECIAL_SPLITS
    global SPECIAL_SPLIT_PAGES
    global SPECIAL_SPLIT_HSPLITS
    global SPECIAL_SPLIT_VSPLITS
    global SPECIAL_SPLIT_BOOLEANS
    global SPECIAL_SPLIT_HOVERLAP
    global SPECIAL_CONTRASTS
    global SPECIAL_CONTRAST_PAGES
    global SPECIAL_CONTRAST_DARKS
    global SPECIAL_CONTRAST_LIGHTS
    global PADDING_COLOR
    global GUI_PREVIEW_SIZE


    clean_temp = "--clean" in sys.argv
    USE_DITHERING = "--no-dither" not in sys.argv  # Inverted logic
    OVERLAP = "--overlap" in sys.argv
    THUMBNAIL_HIGHLIGHT_ACTIVE = "--no-thumb-highlight" not in sys.argv
    SPLIT_SPREADS = "--split-spreads" in sys.argv
    SPLIT_ALL = "--split-all" in sys.argv
    SKIP_ON = "--skip" in sys.argv
    ONLY_ON = "--only" in sys.argv
    DONT_SPLIT = "--dont-split" in sys.argv
    CONTRAST_BOOST = "--contrast-boost" in sys.argv
    MARGIN = "--margin" in sys.argv or "--margins" in sys.argv # being nice since easy mistake.
    INCLUDE_OVERVIEWS = "--include-overviews" in sys.argv
    SIDEWAYS_OVERVIEWS = "--sideways-overviews" in sys.argv
    SELECT_OVERVIEWS = "--select-overviews" in sys.argv
    IS_MANGA = "--manga" in sys.argv
    SPECIAL_SPLITS = "--special-split" in sys.argv
    SPECIAL_CONTRASTS = "--special-contrast" in sys.argv
    THUMBNAIL_WIDTH = 0
    START_PAGE = False
    STOP_PAGE = False
    SAMPLE_SET = "--sample-set" in sys.argv
    SPLIT_SPREADS_PAGES = []
    SKIP_PAGES = []
    ONLY_PAGES = []
    DONT_SPLIT_PAGES = []
    SELECT_OV_PAGES = []
    DESIRED_V_OVERLAP_SEGMENTS = 0
    SET_H_OVERLAP_SEGMENTS = 0
    if OVERLAP or "--vsplit-target" in sys.argv or "-hsplit-count" in sys.argv:
        # OVERLAP either explicitly or implicitly asked for, and we need real defaults.
        DESIRED_V_OVERLAP_SEGMENTS = 3
        SET_H_OVERLAP_SEGMENTS = 1
    MINIMUM_V_OVERLAP_PERCENT = 5
    SET_H_OVERLAP_PERCENT = 70
    MAX_SPLIT_WIDTH = 800
    CONTRAST_VALUE = False
    SPECIAL_SPLIT_PAGES = []
    SPECIAL_SPLIT_HSPLITS = []
    SPECIAL_SPLIT_VSPLITS = []
    SPECIAL_SPLIT_BOOLEANS = []
    SPECIAL_SPLIT_HOVERLAP = []
    SPECIAL_CONTRAST_PAGES = []
    SPECIAL_CONTRAST_DARKS = []
    SPECIAL_CONTRAST_LIGHTS = []
    PADDING_COLOR = 255

    if "--pad-black" in sys.argv:
        PADDING_COLOR = 0

    #GUI Globals
    global SCROLL_FRAME_REF
    SCROLL_FRAME_REF = None
    global GUI_COLUMNS
    # global GUI_PAGE
    global GUI_PAGE_LIMIT

    GUI_COLUMNS = 3
    # GUI_PAGE = 0
    GUI_PAGE_LIMIT = 72  #with three columns, this is 24 rows. 
    GUI_PREVIEW_SIZE = 600

    if GUIMODE: 
        def refresh_page_canvas(page_index, what_changed, scroll_frame_ref):
            # what changed options:
            # "initial" - canvas initial creation
            # "pagination" - redraw due to page change.
            # "skip" - toggle whether page is skipped
            # "dontsplit" - toggle whether page is exempt from splitting.
            # "selectoverviews" - togger whether page gets a preview before its splits.
            # "margin"
            # "marginrefresh"
            # "commandline"
            metadata_obj = scroll_frame_ref.page_metadata[page_index]
            if page_index < 3 or (not what_changed == "initial" and not what_changed == "marginrefresh" and not what_changed == "pagination"
                and not what_changed == "outlined" and not what_changed == "shaded" and not what_changed == "preview" and not what_changed == "contrastrefresh"):
                print(f"State of {what_changed} modified for page {metadata_obj.page_num} display.")
            replace_canvas = metadata_obj.canvas_reference
            replace_img = metadata_obj.photo_reference
            segshow_img = metadata_obj.image_reference.convert('L')  # will be used to show the chunks on rollover.
            if replace_canvas:
                if scroll_frame_ref.g_previewTK.get():
                    # This will be a "show with approximate contrast" setting.
                    darkval = scroll_frame_ref.contrast_dark_input.get()
                    lightval = scroll_frame_ref.contrast_light_input.get()
                    if darkval == "":
                        darkval = "0"
                    if lightval == "":
                        lightval = darkval
                    if metadata_obj.photo_reference_dithered and metadata_obj.prd_dark_contrast_used == darkval and metadata_obj.prd_light_contrast_used == lightval:
                        # it's what we used before, use it again.
                        replace_img = metadata_obj.photo_reference_dithered
                    else:
                        dither_img = metadata_obj.image_reference.convert('L')
                        # dither_img = dither_img.resize((metadata_obj.width*2, metadata_obj.height*2), Image.Resampling.LANCZOS) 
                        dither_img = contrast_boost_image(dither_img, need_boost=True, contrast_values=f"{darkval},{lightval}", page_num = page_index + 1)
                        dither_img = dither_img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                        segshow_img = contrast_boost_image(segshow_img, need_boost=True, contrast_values=f"{darkval},{lightval}", page_num = page_index + 1)
                        # dither_img = dither_img.convert('L')
                        # dither_img = dither_img.resize((metadata_obj.width, metadata_obj.height), Image.Resampling.LANCZOS) 
                        replace_img = ImageTk.PhotoImage(dither_img)
                        # replace_img = replace_img._PhotoImage__photo.subsample(2,2)
                        metadata_obj.photo_reference_dithered = replace_img
                        metadata_obj.prd_dark_contrast_used = darkval
                        metadata_obj.prd_light_contrast_used = lightval
                replace_canvas.delete("all")
                replace_canvas.create_image(0, 0, image=replace_img, anchor='nw') # restore or init canvas to unaltered base image.
                # so long as it's not None, which which would mean it's currently undisplayed due to pagination.
            width = metadata_obj.width
            height = metadata_obj.height
            # skip display
            if metadata_obj.skipTK.get():
                # this image is a skip, so let's grey it out and quit.
                if replace_canvas:
                    # so long as it's not None, which which would mean it's currently undisplayed due to pagination.
                    replace_overlay_img = Image.new('RGBA', (width, height), color=(50, 50, 50, 220))
                    newPhoto = ImageTk.PhotoImage(replace_overlay_img)
                    metadata_obj.overlay_reference = newPhoto
                    replace_canvas.create_image(0, 0, image=newPhoto, anchor='nw')
                return True
            if replace_canvas:
                # so long as it's not None, which which would mean it's currently undisplayed due to pagination.
                overlay_img = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
                rollover_img = Image.new('LA', (width, height), color=(0,224))
                draw = ImageDraw.Draw(overlay_img)
                # margin display
                if True and not metadata_obj.dont_splitTK.get() and not metadata_obj.split_spreadsTK.get(): 
                    # margins are active and we're segmenting this page, so they should be shown.
                    # draw.rectangle((20,20,width-20,height-20), outline=(0,0,255,128), width=2)
                    top = int(height * float(margin_top.get()) / 100.0)
                    bottom = height - int(height * float(margin_bottom.get()) / 100.0)
                    left = int(width * float(margin_left.get()) / 100.0)
                    right = width - int(width * float(margin_right.get()) / 100.0)
                    # draw.rectangle((left,top,right,bottom), outline=(0,0,255,128), width=2)
                    draw.rectangle((0,0,left,height), fill=(50, 50, 50, 220))
                    draw.rectangle((0,0,width,top), fill=(50, 50, 50, 220))
                    draw.rectangle((right,0,width,height), fill=(50, 50, 50, 220))
                    draw.rectangle((0,bottom,width,height), fill=(50, 50, 50, 220))
                    # draw.rectangle((left,top,right,bottom), outline=(0,0,255,128), width=2)
                # Put our new overlay in place.
                elif metadata_obj.split_spreadsTK.get():
                    # show center divider since it's a split spread page. 
                    hcenter = width // 2
                    draw.rectangle((hcenter-3,0,hcenter+3,height), fill=(50,50,50,255))


                if not metadata_obj.dont_splitTK.get() and scroll_frame_ref.g_overlapTK.get():
                    # we need to show how it will be split up. (for now not worrying about special splits or split spreads or max width (yet))
                    number_of_h_segments = 1
                    if (scroll_frame_ref.g_hsplitTargetTK.get()):
                        number_of_h_segments = int(scroll_frame_ref.g_hsplitTargetTK.get())
                    h_overlap_percent = 45
                    if (scroll_frame_ref.g_hsplitOverlapTK.get()):
                        h_overlap_percent = int(scroll_frame_ref.g_hsplitOverlapTK.get())
                    hsplit_max_width = MAX_SPLIT_WIDTH
                    if (scroll_frame_ref.g_hsplitMaxWidthTK.get()):
                        hsplit_max_width = int(scroll_frame_ref.g_hsplitMaxWidthTK.get())
                    if metadata_obj.split_spreadsTK.get():
                        width = width // 2
                        top = int(height * float(margin_top.get()) / 100.0)
                        bottom = height - int(height * float(margin_bottom.get()) / 100.0)
                        left = int(width * float(margin_left.get()) * 2 / 100.0) # doubled because of halving
                        right = width - 5; #leave room for center split bar. 
                    else:
                        top = int(height * float(margin_top.get()) / 100.0)
                        bottom = height - int(height * float(margin_bottom.get()) / 100.0)
                        left = int(width * float(margin_left.get()) / 100.0)
                        right = width - int(width * float(margin_right.get()) / 100.0)
                    cropped_width = right - left
                    local_max_width = int(hsplit_max_width / 800.0 * cropped_width)
                    # if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    #     special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    #     number_of_h_segments = SPECIAL_SPLIT_HSPLITS[special_split_pos]
                    #     h_overlap_percent = SPECIAL_SPLIT_HOVERLAP[special_split_pos]
                    total_calculated_width = local_max_width * number_of_h_segments - int((number_of_h_segments - 1) * (local_max_width * 0.01 * h_overlap_percent))
                        # so, 1 = 800. 2 with 33% overlap = 1334, 3 with 33% overlap = 1868px, etc.
                    established_scale = total_calculated_width * 1.0 / cropped_width
                        # so for 2000px wide source, 1= 0.4, 2=0.667, etc. 
                    # print("cropped_width:", cropped_width)
                    # print("total_calculated_width:", total_calculated_width)

                    overlapping_width = int(local_max_width / established_scale // 1)
                    # print("overlapping_width:", overlapping_width)
                    # print("total_calculated_width:", total_calculated_width)
                    shiftover_to_overlap = 0
                    if number_of_h_segments > 1:
                        shiftover_to_overlap = overlapping_width - (overlapping_width * number_of_h_segments - cropped_width) // (number_of_h_segments - 1)
                    # print("shiftover_to_overlap:", shiftover_to_overlap)
                    number_of_v_segments = 2
                    if (scroll_frame_ref.g_vsplitTargetTK.get()):
                        number_of_v_segments = int(scroll_frame_ref.g_vsplitTargetTK.get()) - 1
                    minimum_v_overlap = 5
                    if (scroll_frame_ref.g_vsplitMinOverlapTK.get()):
                        minimum_v_overlap = int(scroll_frame_ref.g_vsplitMinOverlapTK.get())

                    # if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    #     special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    #     number_of_v_segments = SPECIAL_SPLIT_VSPLITS[special_split_pos]-1
                    #     minimum_v_overlap = -100
                    # letter_keys = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z"]
                    # letter_keys_hsplit = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z"]
                    # if IS_MANGA:
                    #     letter_keys_hsplit.reverse()

                    cropped_height = bottom - top
                    overlapping_height = int(480.0/800 * cropped_width / established_scale // 1)
                    # print("overlapping_height:", overlapping_height)
                    # print("cropped_height:", cropped_height)
                    shiftdown_to_overlap = 9999
                    while number_of_v_segments < 26 and (shiftdown_to_overlap * 1.0 / overlapping_height) > (1.0 - .01 * minimum_v_overlap):
                        # iterate until we have a number of segments that cover the page with sufficient overlap.
                        # the first iteration should fix the 99999 thing and set up our "base" attempt.
                        number_of_v_segments += 1
                        # print("aaashiftdown_to_overlap:", shiftdown_to_overlap)
                        shiftdown_to_overlap = 0
                        # print("bbbshiftdown_to_overlap:", shiftdown_to_overlap)
                        if number_of_v_segments > 1:
                            # print("(overlapping_height * number_of_v_segments - cropped_height):", (overlapping_height * number_of_v_segments - cropped_height))
                            # print("(number_of_v_segments - 1):", (number_of_v_segments - 1))
                            # print("calc:", (overlapping_height * number_of_v_segments - cropped_height) / (number_of_v_segments - 1))
                            shiftdown_to_overlap = overlapping_height - (overlapping_height * number_of_v_segments - cropped_height) // (number_of_v_segments - 1)
                            # print("zzzshiftdown_to_overlap:", shiftdown_to_overlap)


                    # Mark overlapping segments that would fill the screen (at our scale)
                    v = 0
                    use_segment_list = []
                    # if SPECIAL_SPLITS and page_num in SPECIAL_SPLIT_PAGES:
                    #     special_split_pos = SPECIAL_SPLIT_PAGES.index(page_num)
                    #     use_segment_list = SPECIAL_SPLIT_BOOLEANS[special_split_pos]
                    #     print("special split for page:",SPECIAL_SPLIT_PAGES[special_split_pos]," segment list:",use_segment_list)
                    # print("number of h segments:", number_of_h_segments)
                    # print("number of v segments:", number_of_v_segments)
                    overlay_img2 = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
                    draw2 = ImageDraw.Draw(overlay_img2)

                    # how much space would it take to show all the slices side by side.
                    segshow_req_width = (cropped_width-(shiftover_to_overlap*(number_of_h_segments-1))) * number_of_h_segments + 20 * (number_of_h_segments-1) + 30
                    segshow_req_height = (cropped_height-(shiftdown_to_overlap*(number_of_v_segments-1))) * number_of_v_segments + 20 * (number_of_v_segments-1) + 30
                    # how much would we need to scale it down to show that
                    segshow_hscale = width * 1.0 / segshow_req_width
                    segshow_scale = height * 1.0 / segshow_req_height
                    # use the smaller of the two.
                    if segshow_scale > segshow_hscale:
                        segshow_scale = segshow_hscale
                    # segshowdraw = ImageDraw.Draw(rollover_img)

                    while v < number_of_v_segments:
                        # print("v:", v)
                        h = 0
                        while h < number_of_h_segments:
                            # segment = img.crop((shiftover_to_overlap*h, shiftdown_to_overlap*v, width-(shiftover_to_overlap*(number_of_h_segments-h-1)), height-(shiftdown_to_overlap*(number_of_v_segments-v-1))))
                            # draw.rectangle((shiftover_to_overlap*h+left+(v+1)*3, shiftdown_to_overlap*v+top+(v+1)*2, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+left+(v+1)*3, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top+(v+1)*3), outline=(0,0,0,160), width=4)

                            if v > 0 and scroll_frame_ref.g_shadedTK.get() and overlapping_height - shiftdown_to_overlap > 0:
                                draw.rectangle((shiftover_to_overlap*h+left, shiftdown_to_overlap*v+top, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+left, shiftdown_to_overlap*v+top+(overlapping_height - shiftdown_to_overlap)), fill=(96,96,127,150))
                            
                            if h > 0 and scroll_frame_ref.g_shadedTK.get():
                                draw2.rectangle((shiftover_to_overlap*h+left, shiftdown_to_overlap*v+top, shiftover_to_overlap*h+left+(overlapping_width - shiftover_to_overlap), cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top), fill=(96,127,96,100))
                                over_photo2 = ImageTk.PhotoImage(overlay_img2)
                                metadata_obj.overlay_reference2 = over_photo2  # to prevent garbage collection?
                                replace_canvas.create_image(0, 0, image=over_photo2, anchor='nw')
 
                            if scroll_frame_ref.g_outlinedTK.get():
                                draw.rectangle((shiftover_to_overlap*h+left+v*1-1, shiftdown_to_overlap*v+top-1, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+left+v*1+1, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top+1), outline=(255,255,255,255), width=7)
                                draw.rectangle((shiftover_to_overlap*h+left+v*1+1, shiftdown_to_overlap*v+top+1, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+left+v*1-1, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top-1), outline=(255,0,0,255), width=3)                            # if number_of_h_segments > 1:
                           
                            if segshow_img:
                                segshow_crop_img = segshow_img.crop((shiftover_to_overlap*h+left, shiftdown_to_overlap*v+top, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+left, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top))
                                segshow_chunk_width = int(segshow_crop_img.size[0] * segshow_scale)
                                segshow_chunk_height = int(segshow_crop_img.size[1] * segshow_scale)
                                segshow_hcentering = (width - (segshow_chunk_width * number_of_h_segments + 20 * (number_of_h_segments-1))) // 2
                                segshow_vcentering = (height - (segshow_chunk_height * number_of_v_segments + 20 * (number_of_v_segments-1))) // 2
                                segshow_crop_img = segshow_crop_img.resize((segshow_chunk_width, segshow_chunk_height), Image.Resampling.LANCZOS)
                                # segshow_crop_img = segshow_crop_img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                                segshow_crop_img = segshow_crop_img.convert('L')
                                rollover_img.paste(segshow_crop_img,((20+segshow_chunk_width)*h+segshow_hcentering, (20+segshow_chunk_height)*v+segshow_vcentering))
                                # crop_area = (0, 0, 200, 200) 
                                # cropped_img = original_img.crop(crop_area)

                            if metadata_obj.split_spreadsTK.get():
                                local_left = width + 5
                                if v > 0 and scroll_frame_ref.g_shadedTK.get() and overlapping_height - shiftdown_to_overlap > 0:
                                    draw.rectangle((shiftover_to_overlap*h+local_left, shiftdown_to_overlap*v+top, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+local_left, shiftdown_to_overlap*v+top+(overlapping_height - shiftdown_to_overlap)), fill=(96,96,127,150))
                                
                                if h > 0 and scroll_frame_ref.g_shadedTK.get():
                                    draw2.rectangle((shiftover_to_overlap*h+local_left, shiftdown_to_overlap*v+top, shiftover_to_overlap*h+local_left+(overlapping_width - shiftover_to_overlap), cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top), fill=(96,127,96,100))
                                    over_photo2 = ImageTk.PhotoImage(overlay_img2)
                                    metadata_obj.overlay_reference2 = over_photo2  # to prevent garbage collection?
                                    replace_canvas.create_image(0, 0, image=over_photo2, anchor='nw')
    
                                if scroll_frame_ref.g_outlinedTK.get():
                                    draw.rectangle((shiftover_to_overlap*h+local_left+v*1-1, shiftdown_to_overlap*v+top-1, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+local_left+v*1+1, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top+1), outline=(255,255,255,255), width=7)
                                    draw.rectangle((shiftover_to_overlap*h+local_left+v*1+1, shiftdown_to_overlap*v+top+1, cropped_width-(shiftover_to_overlap*(number_of_h_segments-h-1))+local_left+v*1-1, cropped_height-(shiftdown_to_overlap*(number_of_v_segments-v-1))+top-1), outline=(255,0,0,255), width=3)                            # if number_of_h_segments > 1:

                            #     output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}_{letter_keys_hsplit[h]}.png"
                            # else:
                            #     output = output_path_base.parent / f"{page_num:04d}{suffix}_3_{letter_keys[v]}.png"
                            # if THUMBNAIL_WIDTH > 0:
                            #     if THUMBNAIL_HIGHLIGHT_ACTIVE:
                            #         highlight_opacity = 96
                            #         thumbnail_overlay = Image.new('LA', img_thumbnail.size)
                            #         draw_thumb_overlay = ImageDraw.Draw(thumbnail_overlay)
                            #         thumb_region_right = int(thumbnail_height - shiftdown_to_overlap*v*thumbnail_scale)
                            #         thumb_region_top = int(shiftover_to_overlap*h*thumbnail_scale)
                            #         thumb_region_left = int(thumbnail_height - shiftdown_to_overlap*v*thumbnail_scale - overlapping_height*thumbnail_scale)
                            #         thumb_region_bottom = int(THUMBNAIL_WIDTH-(shiftover_to_overlap*(number_of_h_segments-h-1))*thumbnail_scale)
                            #         draw_thumb_overlay.rectangle((thumb_region_left,thumb_region_top,thumb_region_right,thumb_region_bottom), fill=(255,highlight_opacity), outline=(PADDING_COLOR,255), width=3)
                            #         img_temp_thumbnail = Image.alpha_composite(img_thumbnail, thumbnail_overlay).convert("L")
                            #         if len(use_segment_list)==0 or use_segment_list[0]=="1":
                            #             size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR, thumbnail=img_temp_thumbnail)    
                            #     else:
                            #         if len(use_segment_list)==0 or use_segment_list[0]=="1":
                            #             size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR, thumbnail=img_thumbnail)
                            # else:
                            #     if len(use_segment_list)==0 or use_segment_list[0]=="1":
                            #         size = save_with_padding(segment_rotated, output, padcolor=PADDING_COLOR)
                            # if len(use_segment_list)>0:
                            #     use_segment_list.pop(0)
                            h += 1
                        v += 1


                over_photo = ImageTk.PhotoImage(overlay_img)
                metadata_obj.overlay_reference = over_photo # Store reference
                replace_canvas.create_image(0, 0, image=over_photo, anchor='nw', tags="my_overlay_"+str(page_index))

                rollover_photo = ImageTk.PhotoImage(rollover_img)
                metadata_obj.rollover_reference = rollover_photo
                metadata_obj.canvas_reference = replace_canvas

                def on_enter(event):
                    canvas = event.widget
                    page_index = int(canvas.gettags("current")[0].split('_overlay_')[1])
                    # print("on enter for", page_index)
                    metadata_obj = SCROLL_FRAME_REF.page_metadata[page_index]
                    metadata_obj.rollover_to_delete = metadata_obj.canvas_reference.create_image(0, 0, image=metadata_obj.rollover_reference, anchor='nw', tags="my2_overlay_"+str(page_index))
                    metadata_obj.canvas_reference.tag_bind("my2_overlay_"+str(page_index), "<Leave>", on_leave)

                def on_leave(event):
                    canvas = event.widget
                    page_index = int(canvas.gettags("current")[0].split('_overlay_')[1])
                    # print("on leave for", page_index)
                    metadata_obj = SCROLL_FRAME_REF.page_metadata[page_index]
                    metadata_obj.canvas_reference.delete(metadata_obj.rollover_to_delete)

                replace_canvas.tag_bind("my_overlay_"+str(page_index), "<Enter>", on_enter)
                # replace_canvas.tag_bind("my_overlay_"+str(page_index), "<Leave>", on_leave)


        def modify_list_in_option(starting_string, number_to_mod, add_it):
            string_to_mod = str(number_to_mod)
            param_name = starting_string.split(' ')[0]
            page_list = starting_string.split(' ')[1].split(',')
            if add_it:
                if not string_to_mod in page_list:
                    page_list.append(string_to_mod)
            else:
                if string_to_mod in page_list:
                    page_list.remove(string_to_mod)
            if len(page_list) > 0:
                page_list.sort(key=int)
                return param_name + " " + ",".join(page_list)
            else:
                return ""

        def refresh_options(page_index, what_changed, scroll_frame_ref):
            metadata_obj = None
            if page_index > -1:
                # this is page-related.
                metadata_obj = scroll_frame_ref.page_metadata[page_index]
            if page_index < 3 or (not what_changed == "initial" and not what_changed == "marginrefresh"):
                if metadata_obj:
                    print(f"Updating {what_changed} options for page {metadata_obj.page_num}.")
                else:
                    print(f"Updating {what_changed} global option.")
            start_value = options_box.get("1.0","end-1c")
            split_values = start_value.split(" --")
            find_index = 0
            found_it = False
            for val in split_values:
                if what_changed == "skip" and split_values[find_index].startswith("skip "):
                    found_it = True
                    new_bool=metadata_obj.skipTK.get()
                    split_values[find_index] = modify_list_in_option(split_values[find_index], metadata_obj.page_num, new_bool)
                if what_changed == "dontsplit" and split_values[find_index].startswith("dont-split "):
                    found_it = True
                    new_bool=metadata_obj.dont_splitTK.get()
                    split_values[find_index] = modify_list_in_option(split_values[find_index], metadata_obj.page_num, new_bool)
                if what_changed == "selectoverviews" and split_values[find_index].startswith("select-overviews "):
                    found_it = True
                    new_bool=metadata_obj.select_overviewsTK.get()
                    split_values[find_index] = modify_list_in_option(split_values[find_index], metadata_obj.page_num, new_bool)
                if what_changed == "splitspreads" and split_values[find_index].startswith("split-spreads "):
                    found_it = True
                    new_bool=metadata_obj.split_spreadsTK.get()
                    split_values[find_index] = modify_list_in_option(split_values[find_index], metadata_obj.page_num, new_bool)
                if what_changed == "overlap" and split_values[find_index] == "overlap":
                    found_it = True
                    split_values[find_index] = ""
                if what_changed == "overviews" and split_values[find_index] == "include-overviews":
                    found_it = True
                    split_values[find_index] = ""
                if what_changed == "sideways" and split_values[find_index] == "sideways-overviews":
                    found_it = True
                    split_values[find_index] = ""
                if what_changed == "manga" and split_values[find_index] == "manga":
                    found_it = True
                    split_values[find_index] = ""
                if what_changed == "padblack" and split_values[find_index] == "pad-black":
                    found_it = True
                    split_values[find_index] = ""
                if what_changed == "margin" and (split_values[find_index].startswith("margin") or split_values[find_index].startswith("margins")):
                    found_it = True
                    margin_values = []
                    margin_values.append(margin_leftTK.get())
                    margin_values.append(margin_topTK.get())
                    margin_values.append(margin_rightTK.get())
                    margin_values.append(margin_bottomTK.get())
                    margin_values_str = "???"
                    if margin_values[1] != "" or margin_values[2] != "" or margin_values[3] != "":
                        margin_values_str = "margin " + ",".join(margin_values)
                    elif margin_values[0] == "":
                        margin_values_str = ""
                    else:
                        margin_values_str = "margin " + margin_values[0]
                    split_values[find_index] = margin_values_str
                if what_changed == "contrast" and split_values[find_index].startswith("contrast"):
                    found_it = True
                    contrast_values = []
                    contrast_values.append(scroll_frame_ref.contrast_dark_input.get())
                    contrast_values.append(scroll_frame_ref.contrast_light_input.get())
                    contrast_values_str = "???"
                    if contrast_values[1] != "":
                        contrast_values_str = "contrast-boost " + ",".join(contrast_values)
                    elif contrast_values[0] == "":
                        contrast_values_str = ""
                    else:
                        contrast_values_str = "contrast-boost " + contrast_values[0]
                    split_values[find_index] = contrast_values_str
                find_index += 1
            if found_it:
                # is it now blank? remove emptys from list.
                split_values[:] = [x for x in split_values if x]
            else:
                # we didn't find it, need to add it afresh.
                if what_changed == "skip" and metadata_obj.skipTK.get():
                    split_values.append("skip " + str(metadata_obj.page_num))
                if what_changed == "dontsplit" and metadata_obj.dont_splitTK.get():
                    split_values.append("dont-split " + str(metadata_obj.page_num))
                if what_changed == "selectoverviews" and metadata_obj.select_overviewsTK.get():
                    split_values.append("select-overviews " + str(metadata_obj.page_num))
                if what_changed == "splitspreads" and metadata_obj.split_spreadsTK.get():
                    split_values.append("split-spreads " + str(metadata_obj.page_num))
                if what_changed == "overlap" and scroll_frame_ref.g_overlapTK.get():
                    split_values.append("overlap")
                if what_changed == "overviews" and scroll_frame_ref.g_overviewsTK.get():
                    split_values.append("include-overviews")
                if what_changed == "sideways" and scroll_frame_ref.g_sidewaysTK.get():
                    split_values.append("sideways-overviews")
                if what_changed == "manga" and scroll_frame_ref.g_mangaTK.get():
                    split_values.append("manga")
                if what_changed == "padblack" and scroll_frame_ref.g_padBlackTK.get():
                    split_values.append("pad-black")
                if what_changed == "margin":
                    margin_values = []
                    margin_values.append(margin_leftTK.get())
                    margin_values.append(margin_topTK.get())
                    margin_values.append(margin_rightTK.get())
                    margin_values.append(margin_bottomTK.get())
                    margin_values_str = "???"
                    if margin_values[1] != "" or margin_values[2] != "" or margin_values[3] != "":
                        margin_values_str = "margin " + ",".join(margin_values)
                    elif margin_values[0] == "":
                        margin_values_str = ""
                    else:
                        margin_values_str = "margin " + margin_values[0]
                    split_values.append(margin_values_str)
                if what_changed == "contrast":
                    contrast_values = []
                    contrast_values.append(scroll_frame_ref.contrast_dark_input.get())
                    contrast_values.append(scroll_frame_ref.contrast_light_input.get())
                    contrast_values_str = "???"
                    if contrast_values[1] != "":
                        contrast_values_str = "contrast-boost " + ",".join(contrast_values)
                    elif contrast_values[0] == "":
                        contrast_values_str = ""
                    else:
                        contrast_values_str = "contrast-boost " + contrast_values[0]
                    split_values.append(contrast_values_str)
            new_value = " --".join(split_values)
            options_box.delete("1.0", tk.END)
            options_box.insert("1.0", new_value)

        def parse_options(scroll_frame_ref):
            current_options = options_box.get("1.0","end-1c")
            # if check_for == "margin":
            #     # margin entry boxes changed, we have to update the options string.
            #     margin_values = []
            #     margin_values.append(margin_leftTK.get())
            #     margin_values.append(margin_topTK.get())
            #     margin_values.append(margin_rightTK.get())
            #     margin_values.append(margin_bottomTK.get())
            #     margin_values_str = "auto"
            #     if margin_values[1] != "":
            #         print("looking for margin changes:", margin_values)
            #         margin_values_str = ",".join(margin_values)
            #         print("margin_values_str:", margin_values_str)
            #     if "--margins " in current_options:
            #         split_at_margins = current_options.split("--margins ")
            #         split_second_part = split_at_margins[1].split(" --")
            #         if "--" not in split_second_part[0]:
            #             split_second_part[0] = margin_values_str
            #             current_options = split_at_margins[0] + "--margins " + " --".join(split_second_part)
            #             print("new current_options:", current_options)
            #     else:
            #         current_options = current_options + " --margins " + margin_values_str
            # elif check_for =="contrast":
            #     contrast_values = ""
            split_values = current_options.split(" --")
            split_previous = scroll_frame_ref.previous_options.split(" --")
            update_overlay_list = []
            for val in split_values:
                if not val in split_previous:
                    # this parameter has changed!
                    if val.startswith("skip "):
                        page_list = val.split(' ')[1].split(',')
                        # print("skips changed",page_list)
                        for meta_obj in scroll_frame_ref.page_metadata:
                            # print(meta_obj.page_num,(meta_obj.skipTK.get() == 1),(str(meta_obj.page_num) in page_list))
                            if (meta_obj.skipTK.get() == 1) != (str(meta_obj.page_num) in page_list):
                                # There's a mismatch between checkbox and list.
                                meta_obj.skipTK.set(str(meta_obj.page_num) in page_list) #set checkbox
                                update_overlay_list.append(meta_obj.page_index) #mark it for visual update.
                    if val.startswith("dont-split "):
                        page_list = val.split(' ')[1].split(',')
                        # print("dont-split changed",page_list)
                        for meta_obj in scroll_frame_ref.page_metadata:
                            # print(meta_obj.page_num,(meta_obj.dont_splitTK.get() == 1),(str(meta_obj.page_num) in page_list))
                            if (meta_obj.dont_splitTK.get() == 1) != (str(meta_obj.page_num) in page_list):
                                # There's a mismatch between checkbox and list.
                                meta_obj.dont_splitTK.set(str(meta_obj.page_num) in page_list) #set checkbox
                                update_overlay_list.append(meta_obj.page_index) #mark it for visual update.
                    if val.startswith("select-overviews "):
                        page_list = val.split(' ')[1].split(',')
                        # print("select-overviews changed",page_list)
                        for meta_obj in scroll_frame_ref.page_metadata:
                            # print(meta_obj.page_num,(meta_obj.select_overviewsTK.get() == 1),(str(meta_obj.page_num) in page_list))
                            if (meta_obj.select_overviewsTK.get() == 1) != (str(meta_obj.page_num) in page_list):
                                # There's a mismatch between checkbox and list.
                                meta_obj.select_overviewsTK.set(str(meta_obj.page_num) in page_list) #set checkbox
                                update_overlay_list.append(meta_obj.page_index) #mark it for visual update.
                    if val.startswith("split-spreads "):
                        page_list = val.split(' ')[1].split(',')
                        # print("select-overviews changed",page_list)
                        for meta_obj in scroll_frame_ref.page_metadata:
                            # print(meta_obj.page_num,(meta_obj.select_overviewsTK.get() == 1),(str(meta_obj.page_num) in page_list))
                            if (meta_obj.split_spreadsTK.get() == 1) != (str(meta_obj.page_num) in page_list):
                                # There's a mismatch between checkbox and list.
                                meta_obj.split_spreadsTK.set(str(meta_obj.page_num) in page_list) #set checkbox
                                update_overlay_list.append(meta_obj.page_index) #mark it for visual update.
                    if val.startswith("margin ") or val.startswith("margins "):
                        margin_list = val.split(' ')[1].split(',')
                        # print("margins changed",margin_list)
                        if len(margin_list) == 1 and margin_list[0] == "0":
                            margin_left.set("0")
                            margin_top.set("")
                            margin_right.set("")
                            margin_bottom.set("")
                        if len(margin_list) == 1 and margin_list[0] == "auto":
                            margin_left.set("auto")
                            margin_top.set("")
                            margin_right.set("")
                            margin_bottom.set("")
                        elif len(margin_list) == 1:
                            margin_left.set(margin_list[0])
                            margin_top.set("")
                            margin_right.set("")
                            margin_bottom.set("")
                        else:
                            margin_list.append("0")
                            margin_list.append("0")
                            margin_left.set(margin_list[0])
                            margin_top.set(margin_list[1])
                            margin_right.set(margin_list[2])
                            margin_bottom.set(margin_list[3])
                        for metadata_obj in scroll_frame_ref.page_metadata:
                            # print(metadata_obj.page_num)
                            refresh_page_canvas(metadata_obj.page_index, "marginrefresh", scroll_frame_ref)
                    if val.startswith("contrast-boost "):
                        boost_list = val.split(' ')[1].split(',')
                        #print("contrast changed",boost_list)
                        if len(boost_list) == 1:
                            scroll_frame_ref.contrast_dark_input.set(boost_list[0])
                            scroll_frame_ref.contrast_light_input.set(boost_list[0])
                        elif len(boost_list) > 1:
                            scroll_frame_ref.contrast_dark_input.set(boost_list[0])
                            scroll_frame_ref.contrast_light_input.set(boost_list[1])
                        else:
                            scroll_frame_ref.contrast_dark_input.set("")
                            scroll_frame_ref.contrast_light_input.set("")
                        for metadata_obj in scroll_frame_ref.page_metadata:
                            refresh_page_canvas(metadata_obj.page_index, "contrastrefresh", scroll_frame_ref)

            scroll_frame_ref.g_overlapTK.set(value="overlap" in split_values)
            scroll_frame_ref.g_overviewsTK.set(value="include-overviews" in split_values)
            scroll_frame_ref.g_sidewaysTK.set(value="sideways-overviews" in split_values)
            scroll_frame_ref.g_mangaTK.set(value="manga" in split_values)
            scroll_frame_ref.g_padBlackTK.set(value="pad-black" in split_values)

            if len(update_overlay_list) > 0:
                for index_to_update in update_overlay_list:
                    refresh_page_canvas(index_to_update, "commandline", scroll_frame_ref)
            scroll_frame_ref.previous_options = current_options

        def on_key_release(event):
            # Callback function that runs on every key release.
            # The event object has a .widget attribute that refers to the triggering widget
            # current_text = event.widget.get("1.0","end-1c")
            # print("keystroke,", event.widget.get())
            parse_options(SCROLL_FRAME_REF)
            # You can add your function logic here

        def on_key_release_margin(event):
            print("margin keystroke,", event.widget.get())
            refresh_options(-1, "margin", SCROLL_FRAME_REF)
            parse_options(SCROLL_FRAME_REF) # ,check_for="margin")

        def on_key_release_contrast(event):
            refresh_options(-1, "contrast", SCROLL_FRAME_REF)
            parse_options(SCROLL_FRAME_REF) # ,check_for="contrast")

        def on_key_release_segmentation(event):
            print("segmentation keystroke,", event.widget.get())
            refresh_options(-1, "segmentation", SCROLL_FRAME_REF)
            parse_options(SCROLL_FRAME_REF)

        class PageMetadata:
            # A class attribute (shared by all instances)
            skipTK = None  #tk.IntVar(value=0)
            dont_splitTK = None  # tk.IntVar(value=0)
            select_overviewsTK = None #tk.IntVar(value=0)
            split_spreadsTK = None #tk.IntVar(value=0)
            image_reference = None
            photo_reference = None #a TK Photo wrapper. 
            photo_reference_dithered = None #a TK Photo wrapper. 
            prd_dark_contrast_used = "-1"
            prd_light_contrast_used = "-1"
            overlay_reference = None
            overlay_reference2 = None  # used rarely, for horizontal split overlay at this time.
            rollover_reference = None 
            canvas_reference = None
            rollover_to_delete = None
            width = -1
            height = -1

            def __init__(self, page_index):
                # Instance attributes (unique to each object)
                self.page_index = page_index
                self.page_num = page_index + 1

        class CanvasDisplayControls:
            # A class attribute (shared by all instances)
            titleTKlabel = None # A label
            skipTKcb = None  # A checkbutton
            dont_splitTKcb = None  # A checkbutton
            select_overviewsTKcb = None  # A checkbutton
            split_spreadsTKcb = None  # A checkbutton
            previewTK = None
            shadedTK = None
            outlinedTK = None
            canvas_reference = None  # A page display canvas

            def __init__(self, canvas_index):
                # Instance attributes (unique to each object)
                self.canvas_index = canvas_index

        class ScrollableImageFrame(tk.Frame):
            def __init__(self, master, image_paths, *args, **kwargs):
                tk.Frame.__init__(self, master, *args, **kwargs)
                self.image_paths = image_paths
                self.page_metadata = []
                self.canvas_display_and_controls = []
                self.previous_options = ""
                # print("init TK variables")
                self.g_overlapTK = None # tk.IntVar(value=0)
                self.g_overviewsTK = None # tk.IntVar(value=0)
                self.g_sidewaysTK = None # tk.IntVar(value=0)
                self.g_mangaTK = None # tk.IntVar(value=0)
                self.g_padBlackTK = None # tk.IntVar(value=0)
                self.contrast_dark_input = tk.StringVar(value="")
                self.contrast_light_input = tk.StringVar(value="")
                self.g_vsplitTargetTK = tk.StringVar(value="")
                self.g_vsplitMinOverlapTK = tk.StringVar(value="")
                self.g_hsplitTargetTK = tk.StringVar(value="")
                self.g_hsplitOverlapTK = tk.StringVar(value="")
                self.g_hsplitMaxWidthTK = tk.StringVar(value="")
                ## more set below
                # g_shadedTK
                # g_outlinedTK
                # g_segmentation_controls

                # 1. Create a Canvas and a Scrollbar
                self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
                self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
                self.scrollable_frame = tk.Frame(self.canvas)

                # 2. Configure the canvas and scrollbar
                self.scrollable_frame.bind(
                    "<Configure>",
                    lambda e: self.canvas.configure(
                        scrollregion=self.canvas.bbox("all")
                    )
                )
                self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
                self.canvas.configure(yscrollcommand=self.scrollbar.set)

                # 3. Pack the canvas and scrollbar
                self.canvas.pack(side="left", fill="both", expand=True)
                self.scrollbar.pack(side="right", fill="y")

                # Bind mouse wheel scrolling
                self.canvas.bind("<MouseWheel>", self.on_mousewheel)
                if platform.system() == 'Linux':
                    self.canvas.bind("<Button-4>", self.on_mousewheel)
                    self.canvas.bind("<Button-5>", self.on_mousewheel)

                # 4. Load and display images
                self.load_images()
                print("images loaded")
                # print("g_overlapTK:",self.g_overlapTK.get())
                parse_options(self)

            def on_mousewheel(event):
                # Respond to wheel event
                # Windows/macOS use event.delta; Linux uses event.num
                print("Scrollies!")
                if platform.system() == 'Linux':
                    if event.num == 4:
                        self.canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        self.canvas.yview_scroll(1, "units")
                elif platform.system() == 'Windows':
                    # Windows: event.delta is a multiple of 120
                    print("Win scrollies!")
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    # Mac: event.delta is as-is
                    print("Mac scrollies!")
                    self.canvas.yview_scroll(int(-1 * (event.delta)), "units")

            # def on_mousewheel(self, event):
            #     self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

            def skip_clicked(self, page_index):
                refresh_page_canvas(page_index, "skip", self)
                refresh_options(page_index, "skip", self)

            def dontsplit_clicked(self, page_index):
                refresh_page_canvas(page_index, "dontsplit", self)
                refresh_options(page_index, "dontsplit", self)

            def selectoverviews_clicked(self, page_index):
                # refresh_page_canvas(page_index, "selectoverviews", self)  # not needed because no change.
                refresh_options(page_index, "selectoverviews", self)

            def splitspreads_clicked(self, page_index):
                refresh_page_canvas(page_index, "splitspreads", self)
                refresh_options(page_index, "splitspreads", self)

            def load_images(self):
                global GUI_PAGE_LIMIT

                def overlap_clicked():
                    print("overlap clicked")
                    if self.g_overlapTK.get():
                        #turning it on, show the grid frame of controls.
                        self.g_segmentation_controls.grid(row=2,column=0,columnspan=GUI_COLUMNS*2,pady=0)
                    else:
                        self.g_segmentation_controls.grid_remove()
                    refresh_options(-1, "overlap", self)
                    for metadata_obj in self.page_metadata:
                        refresh_page_canvas(metadata_obj.page_index, "outlined", self)

                def overviews_clicked():
                    print("overviews clicked")
                    refresh_options(-1, "overviews", self)

                def sideways_clicked():
                    print("sideways clicked")
                    refresh_options(-1, "sideways", self)

                def manga_clicked():
                    print("maga clicked")
                    refresh_options(-1, "manga", self)

                def padblack_clicked():
                    print("padblack clicked")
                    refresh_options(-1, "padblack", self)

                def outlined_clicked():
                    print("outlined clicked")
                    # refresh_options(-1, "outlined", self)
                    for metadata_obj in self.page_metadata:
                        refresh_page_canvas(metadata_obj.page_index, "outlined", self)

                def shaded_clicked():
                    print("shaded clicked")
                    # refresh_options(-1, "shaded", self)
                    for metadata_obj in self.page_metadata:
                        refresh_page_canvas(metadata_obj.page_index, "shaded", self)

                def preview_clicked():
                    print("preview clicked")
                    # refresh_options(-1, "preview", self)
                    for metadata_obj in self.page_metadata:
                        refresh_page_canvas(metadata_obj.page_index, "preview", self)

                scroll_frame = self.scrollable_frame
               
                top_scroll_controls_frame1 = tk.Frame(scroll_frame)
                top_scroll_controls_frame1.grid(row=0,column=0,columnspan=GUI_COLUMNS*2,pady=0)

                overall_label = tk.Label(top_scroll_controls_frame1, text="Overall Processing Options:")
                overall_label.pack(side=tk.LEFT, anchor="w")

                top_scroll_controls_frame2 = tk.Frame(scroll_frame)
                top_scroll_controls_frame2.grid(row=1,column=0,columnspan=GUI_COLUMNS*2,pady=0)

                self.g_overlapTK = tk.IntVar(value=0)
                # print("overlap confirm",self.g_overlapTK.get())
                checkbox_g1 = tk.Checkbutton(top_scroll_controls_frame2, 
                    text="Overlap segments",
                    variable=self.g_overlapTK,  # Link the variable to the checkbox
                    command=overlap_clicked)     # Call a function when clicked
                checkbox_g1.pack(side=tk.LEFT, anchor="w")
                self.g_overviewsTK = tk.IntVar(value=0)
                checkbox_g2 = tk.Checkbutton(top_scroll_controls_frame2, 
                    text="Use preceding overviews",
                    variable=self.g_overviewsTK,  # Link the variable to the checkbox
                    command=overviews_clicked)     # Call a function when clicked
                checkbox_g2.pack(side=tk.LEFT, anchor="w")
                self.g_sidewaysTK = tk.IntVar(value=0)
                checkbox_g3 = tk.Checkbutton(top_scroll_controls_frame2, 
                    text="Sideways overviews",
                    variable=self.g_sidewaysTK,  # Link the variable to the checkbox
                    command=sideways_clicked)     # Call a function when clicked
                checkbox_g3.pack(side=tk.LEFT, anchor="w")
                self.g_mangaTK = tk.IntVar(value=0)
                checkbox_g4 = tk.Checkbutton(top_scroll_controls_frame2, 
                    text="Manga (R to L)",
                    variable=self.g_mangaTK,  # Link the variable to the checkbox
                    command=manga_clicked)     # Call a function when clicked
                checkbox_g4.pack(side=tk.LEFT, anchor="w")
                self.g_padBlackTK = tk.IntVar(value=0)
                checkbox_g5 = tk.Checkbutton(top_scroll_controls_frame2, 
                    text="Pad with black",
                    variable=self.g_padBlackTK,  # Link the variable to the checkbox
                    command=padblack_clicked)     # Call a function when clicked
                checkbox_g5.pack(side=tk.LEFT, anchor="w")

                top_scroll_controls_frame3 = tk.Frame(scroll_frame)
                self.g_segmentation_controls = top_scroll_controls_frame3
                segmentation_label = tk.Label(top_scroll_controls_frame3, text="Segmentation:")
                segmentation_label.pack(side=tk.LEFT, anchor="w")

                vsplit_target_label = tk.Label(top_scroll_controls_frame3, text="Rows (minimum)")
                vsplit_target_label.pack(side=tk.LEFT, anchor="w")
                vsplitTargetTK = tk.Entry(top_scroll_controls_frame3, textvariable=self.g_vsplitTargetTK, width=2)
                vsplitTargetTK.pack(side=tk.LEFT, padx=(0, 20))
                vsplitTargetTK.bind("<KeyRelease>", on_key_release_segmentation)

                vsplit_min_overlap_label = tk.Label(top_scroll_controls_frame3, text="% Row Overlap needed")
                vsplit_min_overlap_label.pack(side=tk.LEFT, anchor="w")
                vsplitMinOverlapTK = tk.Entry(top_scroll_controls_frame3, textvariable=self.g_vsplitMinOverlapTK, width=4)
                vsplitMinOverlapTK.pack(side=tk.LEFT, padx=(0, 20))
                vsplitMinOverlapTK.bind("<KeyRelease>", on_key_release_segmentation)

                hsplit_target_label = tk.Label(top_scroll_controls_frame3, text="Columns")
                hsplit_target_label.pack(side=tk.LEFT, anchor="w")
                hsplitTargetTK = tk.Entry(top_scroll_controls_frame3, textvariable=self.g_hsplitTargetTK, width=2)
                hsplitTargetTK.pack(side=tk.LEFT, padx=(0, 20))
                hsplitTargetTK.bind("<KeyRelease>", on_key_release_segmentation)

                hsplit_overlap_label = tk.Label(top_scroll_controls_frame3, text="% Column Overlap")
                hsplit_overlap_label.pack(side=tk.LEFT, anchor="w")
                hsplitOverlapTK = tk.Entry(top_scroll_controls_frame3, textvariable=self.g_hsplitOverlapTK, width=4)
                hsplitOverlapTK.pack(side=tk.LEFT, padx=(0, 20))
                hsplitOverlapTK.bind("<KeyRelease>", on_key_release_segmentation)

                hsplit_max_width_label = tk.Label(top_scroll_controls_frame3, text="Max Column Width (px)")
                hsplit_max_width_label.pack(side=tk.LEFT, anchor="w")
                hsplitMaxWidthTK = tk.Entry(top_scroll_controls_frame3, textvariable=self.g_hsplitMaxWidthTK, width=4)
                hsplitMaxWidthTK.pack(side=tk.LEFT, padx=(0, 20))
                hsplitMaxWidthTK.bind("<KeyRelease>", on_key_release_segmentation)

                self.g_outlinedTK = tk.IntVar(value=0)
                checkbox_g5 = tk.Checkbutton(top_scroll_controls_frame3, 
                    text="Preview Borders",
                    variable=self.g_outlinedTK,  # Link the variable to the checkbox
                    command=outlined_clicked)     # Call a function when clicked
                checkbox_g5.pack(side=tk.LEFT, anchor="w")

                self.g_shadedTK = tk.IntVar(value=1)
                checkbox_g6 = tk.Checkbutton(top_scroll_controls_frame3, 
                    text="Preview Overlap Regions",
                    variable=self.g_shadedTK,  # Link the variable to the checkbox
                    command=shaded_clicked)     # Call a function when clicked
                checkbox_g6.pack(side=tk.LEFT, anchor="w")

                if OVERLAP:
                    # it's on, show it.
                    top_scroll_controls_frame3.grid(row=2,column=0,columnspan=GUI_COLUMNS*2,pady=0)


                top_scroll_controls_frame4 = tk.Frame(scroll_frame)
                top_scroll_controls_frame4.grid(row=3,column=0,columnspan=GUI_COLUMNS*2,pady=0)
                segmentation_label = tk.Label(top_scroll_controls_frame4, text="Contrast Boost:")
                segmentation_label.pack(side=tk.LEFT, anchor="w")

                contrast_dark_label = tk.Label(top_scroll_controls_frame4, text="Darker Darks")
                contrast_dark_label.pack(side=tk.LEFT, anchor="w")
                # scroll_frame.contrast_dark_input = tk.StringVar(value="");
                contrast_dark_TK = tk.Entry(top_scroll_controls_frame4, textvariable=self.contrast_dark_input, width=2)
                contrast_dark_TK.pack(side=tk.LEFT, padx=(0, 20))
                contrast_dark_TK.bind("<KeyRelease>", on_key_release_contrast)
                contrast_light_label = tk.Label(top_scroll_controls_frame4, text="Lighter Lights")
                contrast_light_label.pack(side=tk.LEFT, anchor="w")
                # scroll_frame.contrast_light_input = tk.StringVar(value="");
                contrast_light_TK = tk.Entry(top_scroll_controls_frame4, textvariable=self.contrast_light_input, width=2)
                contrast_light_TK.pack(side=tk.LEFT, padx=(0, 20))
                contrast_light_TK.bind("<KeyRelease>", on_key_release_contrast)

                self.g_previewTK = tk.IntVar(value=0)
                checkbox_g5 = tk.Checkbutton(top_scroll_controls_frame4, 
                    text="Preview Approximate Contrast",
                    variable=self.g_previewTK,  # Link the variable to the checkbox
                    command=preview_clicked)     # Call a function when clicked
                checkbox_g5.pack(side=tk.LEFT, anchor="w")

                top_scroll_controls_frame5 = tk.Frame(scroll_frame)
                top_scroll_controls_frame5.grid(row=4,column=0,columnspan=GUI_COLUMNS*2,pady=0)
                spacer_label = tk.Label(top_scroll_controls_frame5, text=" ")
                spacer_label.pack(side=tk.LEFT, anchor="w")

                header_offset = 5 #account for the rows of controls and the spacer. 
                
                if len(self.image_paths) < 100:
                    #let's increase the gui page limit a bit to avoid having pagination with just a few on page 2.
                    GUI_PAGE_LIMIT = 99

                for i, path in enumerate(self.image_paths):
                    try:
                        # Open and resize image (optional, recommended for many images)
                        img = Image.open(path)
                        width, height = img.size
                        # img = img.resize((width*2//3, height*2//3), Image.Resampling.LANCZOS)
                        # width, height = img.size
                        # img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                        # img = img.convert('L')
                        photo = ImageTk.PhotoImage(img)
                        self.page_metadata.append(PageMetadata(i))
                        metadata_obj = self.page_metadata[i];
                        # Store reference
                        metadata_obj.image_reference = img
                        metadata_obj.photo_reference = photo
                        # Store size properties
                        metadata_obj.width = width
                        metadata_obj.height = height

                        if i < GUI_PAGE_LIMIT:
                            self.canvas_display_and_controls.append(CanvasDisplayControls(i))
                            canv_controls_obj = self.canvas_display_and_controls[i]
                            # Create canvas to draw base image and overlay image (with splits and crops) in.
                            pageimage_canvas = tk.Canvas(self.scrollable_frame, width=width, height=height)
                            pageimage_canvas.grid(row=i // GUI_COLUMNS + header_offset, column=(i % GUI_COLUMNS)*2, padx=5, pady=5, sticky=tk.E) # 3 double columns grid layout
                            metadata_obj.canvas_reference = pageimage_canvas # Store reference for one in use.
                            canv_controls_obj.canvas_reference = pageimage_canvas # Store reference for reuse in pagination.
                            # Add the controls and init the associated variables.
                            # set up the surrounding frame
                            control_frame = tk.Frame(self.scrollable_frame)
                            control_frame.grid(row=i // GUI_COLUMNS + header_offset, column=(i % GUI_COLUMNS) * 2 + 1, padx=5, pady=5)
                            # put a title at the top.
                            control_title = tk.Label(control_frame, text=f"page {i+1}")
                            control_title.pack(anchor="w")
                            canv_controls_obj.titleTKlabel = control_title
                            # set up skip property and control
                            metadata_obj.skipTK = tk.IntVar(value=0)
                            checkbox = tk.Checkbutton(control_frame, 
                            text="Skip", 
                            variable=metadata_obj.skipTK,  # Link the variable to the checkbox
                            command=lambda currenti=i: self.skip_clicked(currenti))     # Call a function when clicked
                            checkbox.pack(anchor="w")
                            canv_controls_obj.skipTKcb = checkbox  # store reference to re-config the control later.
                            # set up dont-split property and control
                            metadata_obj.dont_splitTK = tk.IntVar(value=0)
                            checkbox2 = tk.Checkbutton(control_frame, 
                            text="Don't Split", 
                            variable=metadata_obj.dont_splitTK,  # Link the variable to the checkbox
                            command=lambda currenti=i: self.dontsplit_clicked(currenti))     # Call a function when clicked
                            checkbox2.pack(anchor="w")
                            canv_controls_obj.dont_splitTKcb = checkbox2  # store reference to re-config the control later.
                            # set up dont-split property and control
                            metadata_obj.select_overviewsTK = tk.IntVar(value=0)
                            checkbox3 = tk.Checkbutton(control_frame, 
                            text="Precede w/Overview", 
                            variable=metadata_obj.select_overviewsTK,  # Link the variable to the checkbox
                            command=lambda currenti=i: self.selectoverviews_clicked(currenti))     # Call a function when clicked
                            checkbox3.pack(anchor="w")
                            canv_controls_obj.select_overviewsTKcb = checkbox3  # store reference to re-config the control later.
                            # set up split-spread property and control
                            metadata_obj.split_spreadsTK = tk.IntVar(value=0)
                            checkbox4 = tk.Checkbutton(control_frame, 
                            text="Split into two pages",
                            variable=metadata_obj.split_spreadsTK,  # Link the variable to the checkbox
                            command=lambda currenti=i: self.splitspreads_clicked(currenti))     # Call a function when clicked
                            checkbox4.pack(anchor="w")
                            canv_controls_obj.split_spreadsTKcb = checkbox4  # store reference to re-config the control later.

                            # Draw page for the first time
                            refresh_page_canvas(i, "initial", self)
                        else:
                            # we're over our limit, but still need to set up the data structures for later pagination.
                            metadata_obj.canvas_reference = None  #it's not linked to a visible canvas. 
                            metadata_obj.skipTK = tk.IntVar(value=0)
                            metadata_obj.dont_splitTK = tk.IntVar(value=0)
                            metadata_obj.select_overviewsTK = tk.IntVar(value=0)
                            metadata_obj.split_spreadsTK = tk.IntVar(value=0)

                            # Freshen page for the first time (but it won't be drawn because current page not displaying it.)
                            refresh_page_canvas(i, "initial", self)

                    except FileNotFoundError:
                        print(f"Error: Image not found at {path}")
                    except Exception as e:
                        print(f"An error occurred with image {path}: {e}")

        root = tk.Tk()
        root.title("Scrollable Image List")
        root.geometry("1680x1200")

        # Create dummy image files for testing
        # if not os.path.exists("gui_images"):
        #     os.makedirs("gui_images")
        #     # Create some placeholder images (requires Pillow)
        #     for i in range(15):
        #         img = Image.new('RGB', (150, 150), color = (i*10, 100, 150))
        #         img.save(f"gui_images/image_{i+1}.png")

        # Get list of image file paths
        # MARGIN_VALUE = "0"
        # STOP_PAGE = 6
        # USE_DITHERING = False
        # print("sys.argv[1]",sys.argv[1])
        input_dir = Path(sys.argv[1])
        temp_dir = input_dir / "gui_temp_png"
        # Find all CBZ files (including in subdirectories)
        cbz_files = []
        
        # Check current directory
        cbz_files.extend(sorted(input_dir.glob("*.cbz")))
        cbz_files.extend(sorted(input_dir.glob("*.CBZ")))
        cbz_path = cbz_files[0]
        temp_png_path = extract_cbz_to_png(cbz_path, temp_dir, gui_thumbnails=True)
        # STOP_PAGE = False

        global STRING_ARGS
        STRING_ARGS = " ".join(sys.argv)

        def on_closing():
            global STRING_ARGS
            STRING_ARGS = options_box.get("1.0", "end-1c")
            print("new command after edits:", STRING_ARGS)
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        def on_auto_click():
            """This function runs when the button is clicked."""
            print("Button was clicked! This code runs inside the event loop.")
            # You can interact with other widgets here, e.g., update a label.
            # label.config(text=STRING_ARGS)
            margin_left.set("auto")
            margin_top.set("")
            margin_right.set("")
            margin_bottom.set("")
            refresh_options(-1, "margin", SCROLL_FRAME_REF)
            for metadata_obj in scroll_frame.page_metadata:
                # print(metadata_obj.page_num)
                refresh_page_canvas(metadata_obj.page_index, "marginrefresh", SCROLL_FRAME_REF)

        def on_pagination_click(what_page):
            num_pages = len(SCROLL_FRAME_REF.page_metadata)
            new_start = what_page * GUI_PAGE_LIMIT
            new_end = (what_page +1) * GUI_PAGE_LIMIT - 1
            if new_end > num_pages - 1:
                new_end = num_pages - 1
            print(f"Pagination Button {what_page} was clicked! ({new_start}-{new_end})")
            i = 0;
            c = 0;
            while i < num_pages:
                metadata_obj = SCROLL_FRAME_REF.page_metadata[i]
                if i >= new_start and i <= new_end:
                    canvas_obj = SCROLL_FRAME_REF.canvas_display_and_controls[c]
                    canvas_obj.canvas_reference.config(width=metadata_obj.width, height=metadata_obj.height)
                    # make page index i have canvas reference to canvas obj c..
                    metadata_obj.canvas_reference = canvas_obj.canvas_reference
                    # link i's variables to its TK controls.
                    canvas_obj.titleTKlabel.config(text="Page " + str(metadata_obj.page_num))
                    canvas_obj.skipTKcb.config(variable=metadata_obj.skipTK, state=tk.NORMAL, command=lambda currenti=i: SCROLL_FRAME_REF.skip_clicked(currenti))
                    canvas_obj.dont_splitTKcb.config(variable=metadata_obj.dont_splitTK, state=tk.NORMAL, command=lambda currenti=i: SCROLL_FRAME_REF.dontsplit_clicked(currenti))
                    canvas_obj.select_overviewsTKcb.config(variable=metadata_obj.select_overviewsTK, state=tk.NORMAL, command=lambda currenti=i: SCROLL_FRAME_REF.selectoverviews_clicked(currenti))
                    canvas_obj.split_spreadsTKcb.config(variable=metadata_obj.split_spreadsTK, state=tk.NORMAL, command=lambda currenti=i: SCROLL_FRAME_REF.splitspreads_clicked(currenti))
                    # redraw canvas with new page.
                    refresh_page_canvas(i, "pagination", SCROLL_FRAME_REF)
                    c += 1
                else:
                    # set i's canvas reference to None.
                    metadata_obj.canvas_reference = None  # Delinked.
                i += 1
            while c < GUI_PAGE_LIMIT:
                canvas_obj = SCROLL_FRAME_REF.canvas_display_and_controls[c]
                canvas_obj.canvas_reference.delete("all")
                canvas_obj.titleTKlabel.config(text="-")
                canvas_obj.skipTKcb.config(state=tk.DISABLED)
                canvas_obj.dont_splitTKcb.config(state=tk.DISABLED)
                canvas_obj.select_overviewsTKcb.config(state=tk.DISABLED)
                canvas_obj.split_spreadsTKcb.config(state=tk.DISABLED)
                c += 1
                
        top_control_frame = tk.Frame(root)
        top_control_frame.pack(side=tk.TOP, fill=tk.X)
        options_box = tk.Text(top_control_frame, height=10, width=50, font=("Courier", 14, "normal")) 
        options_box.insert("1.0", STRING_ARGS)
        options_box.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10, padx=10)
        options_box.bind("<KeyRelease>", on_key_release)

        #overall margin control
        margin_label = tk.Label(top_control_frame, text="Margins")
        margin_label.pack()
        margin_frame1 = tk.Frame(top_control_frame)
        margin_frame1.pack()
        margin_top = tk.StringVar(value="4.0");
        margin_topTK = tk.Entry(margin_frame1, textvariable=margin_top, width=4)
        margin_topTK.pack()
        margin_topTK.bind("<KeyRelease>", on_key_release_margin)

        margin_frame2 = tk.Frame(top_control_frame)
        margin_frame2.pack()
        margin_left = tk.StringVar(value="2.0");
        margin_leftTK = tk.Entry(margin_frame2, textvariable=margin_left, width=4)
        margin_leftTK.pack(side=tk.LEFT)
        margin_leftTK.bind("<KeyRelease>", on_key_release_margin)
        margin_right = tk.StringVar(value="2.0");
        margin_rightTK = tk.Entry(margin_frame2, textvariable=margin_right, width=4)
        margin_rightTK.pack(side=tk.RIGHT)
        margin_rightTK.bind("<KeyRelease>", on_key_release_margin)

        margin_frame3 = tk.Frame(top_control_frame)
        margin_frame3.pack()
        margin_bottom = tk.StringVar(value="4.0")
        margin_bottomTK = tk.Entry(margin_frame3, textvariable=margin_bottom, width=4)
        margin_bottomTK.pack()
        margin_bottomTK.bind("<KeyRelease>", on_key_release_margin)

        # The 'command' attribute links the button click event to the on_button_click function
        button = tk.Button(top_control_frame, text="Auto", command=on_auto_click)
        button.pack()


        # print("temp dir:",temp_png_path)
        # print("os.listdir(temp_dir):",os.listdir(temp_png_path))
        target_size = GUI_PREVIEW_SIZE
        image_files = [os.path.join(temp_png_path, f) for f in os.listdir(temp_png_path) if f.endswith(f"{target_size}.png")]
        # print("image_files:",image_files)
        image_files.sort()
        scroll_frame = ScrollableImageFrame(root, image_files)
        SCROLL_FRAME_REF = scroll_frame
        scroll_frame.pack(side=tk.TOP, fill="both", expand=True)

        # print("setting up IntVars")
        # scroll_frame.g_overlapTK = tk.IntVar(value=0)
        # scroll_frame.g_overviewsTK = tk.IntVar(value=0)
        # scroll_frame.g_sidewaysTK = tk.IntVar(value=0)

        # scroll_frame.previous_options = ""

        bottom_control_frame = tk.Frame(root)
        bottom_control_frame.pack(side=tk.BOTTOM, fill=tk.X)
        howManyPages = len(SCROLL_FRAME_REF.page_metadata) // GUI_PAGE_LIMIT
        bot_label = tk.Label(bottom_control_frame, text="GUI work by Glenn Loos-Austin")
        if howManyPages:
            bot_label.pack(side=tk.LEFT)
            i = howManyPages
            buttonA = tk.Button(bottom_control_frame, text=str(i * GUI_PAGE_LIMIT + 1) + "–" + str(len(SCROLL_FRAME_REF.page_metadata)), command=lambda currenti=i: on_pagination_click(currenti))
            buttonA.pack(side=tk.RIGHT)
            i -= 1
            while i > -1:
                buttonA = tk.Button(bottom_control_frame, text=str(i * GUI_PAGE_LIMIT + 1) + "–" + str((i+1)*GUI_PAGE_LIMIT), command=lambda currenti=i: on_pagination_click(currenti))
                buttonA.pack(side=tk.RIGHT)
                i -= 1
            pages_label = tk.Label(bottom_control_frame, text="Pages")
            pages_label.pack(side=tk.RIGHT)
        else:
            bot_label.pack()

        root.mainloop()

        print("string_args now:", STRING_ARGS)

        sys.argv = STRING_ARGS.split(" ")

    # args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    
    i = 1
    args = []
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--thumbnail":
            THUMBNAIL_WIDTH = int(sys.argv[i+1])
            print("Will show thumbnail on splits of width:", THUMBNAIL_WIDTH)
            # skip the next arg, as it's thumbnail_width pixels parameter.
            i += 1
        elif arg == "--split-spreads":
            SPLIT_SPREADS_PAGES = sys.argv[i+1].split(',')
            print("Will split spread pages:", SPLIT_SPREADS_PAGES)
            # skip the next arg, as it's split spread pages parameter.
            i += 1
        elif arg == "--skip":
            SKIP_PAGES = sys.argv[i+1].split(',')
            print("Will skip pages:", SKIP_PAGES)
            # skip the next arg, as it's skip pages parameter.
            i += 1
        elif arg == "--only":
            ONLY_PAGES = sys.argv[i+1].split(',')
            print("Will only do pages:", ONLY_PAGES)
            i += 1 #skip next arg
        elif arg == "--dont-split":
            DONT_SPLIT_PAGES = sys.argv[i+1].split(',')
            print("Will not split pages:", DONT_SPLIT_PAGES)
            i += 1 #skip next arg
        elif arg == "--contrast-boost":
            CONTRAST_VALUE = sys.argv[i+1]
            print("Contrast setting:", CONTRAST_VALUE)
            i += 1 #skip next arg
        elif arg == "--margin" or arg== "--margins":
            MARGIN_VALUE = sys.argv[i+1]
            print("Margin setting:", MARGIN_VALUE)
            i += 1 #skip next arg
        elif arg == "--select-overviews":
            SELECT_OV_PAGES = sys.argv[i+1].split(',')
            print("Overviews will be added for pages:", SELECT_OV_PAGES)
            i += 1 #skip next arg
        elif arg == "--start":
            START_PAGE = int(sys.argv[i+1])
            print("Generation will start at page:", START_PAGE)
            i += 1 #skip next arg
        elif arg == "--stop":
            STOP_PAGE = int(sys.argv[i+1])
            print("Generation will stop after page:", STOP_PAGE)
            i += 1 #skip next arg
        elif arg == "--vsplit-target":
            OVERLAP = True  # even if not explicitly set.
            DESIRED_V_OVERLAP_SEGMENTS = int(sys.argv[i+1])
            print("will try to verticallly split into ", DESIRED_V_OVERLAP_SEGMENTS, "segments")
            i += 1 #skip next arg
        elif arg == "--vsplit-min-overlap":
            MINIMUM_V_OVERLAP_PERCENT = float(sys.argv[i+1])
            print("Minimum percentage overlap for vertical splits:", MINIMUM_V_OVERLAP_PERCENT)
            i += 1 #skip next arg
        elif arg == "--hsplit-count":
            OVERLAP = True    # even if not explicitly set.
            SET_H_OVERLAP_SEGMENTS = int(sys.argv[i+1])
            print("will horizontally split into ", SET_H_OVERLAP_SEGMENTS, "segments")
            i += 1 #skip next arg
        elif arg == "--hsplit-overlap":
            SET_H_OVERLAP_PERCENT = float(sys.argv[i+1])
            print("will do this percentage overlap for horizontal splits:", SET_H_OVERLAP_PERCENT)
            i += 1 #skip next arg
        elif arg == "--hsplit-max-width":
            MAX_SPLIT_WIDTH = int(sys.argv[i+1])
            print("max width in pixels for horizontal splits:", MAX_SPLIT_WIDTH)
            i += 1 #skip next arg
        elif arg == "--sample-set":
            SAMPLE_PAGES = sys.argv[i+1].split(',')
            print("Sample Mode for pages:", SAMPLE_PAGES)
            i += 1 #skip next arg
        elif arg == "--special-split":
            specifiers = sys.argv[i+1].split(',')
            for specifier in specifiers:
                SPECIAL_SPLIT_PAGES.append(int(specifier.split('-')[0]))
                SPECIAL_SPLIT_HSPLITS.append(int(specifier.split('-')[1]))
                SPECIAL_SPLIT_VSPLITS.append(int(specifier.split('-')[2]))
                if len(specifier.split('-'))>3:
                    SPECIAL_SPLIT_BOOLEANS.append(list(specifier.split('-')[3]))
                else:
                    SPECIAL_SPLIT_BOOLEANS.append('');
                if len(specifier.split('-'))>4:
                    SPECIAL_SPLIT_HOVERLAP.append(int(specifier.split('-')[4]))
                else:
                    SPECIAL_SPLIT_HOVERLAP.append(SET_H_OVERLAP_PERCENT)
            print("special-split specifier pages:", SPECIAL_SPLIT_PAGES)
            print("special-split specifier booleans:", SPECIAL_SPLIT_BOOLEANS)
            i += 1 #skip next arg
        elif arg == "--special-contrast":
            specifiers = sys.argv[i+1].split(',')
            for specifier in specifiers:
                SPECIAL_CONTRAST_PAGES.append(int(specifier.split('-')[0]))
                SPECIAL_CONTRAST_DARKS.append(int(specifier.split('-')[1]))
                SPECIAL_CONTRAST_LIGHTS.append(int(specifier.split('-')[2]))
            print("special-contrast specifier pages:", SPECIAL_CONTRAST_PAGES)
            i += 1 #skip next arg
        elif arg.startswith("--"):
            pass # do nothing, it's presumably boolean and handled above.
        else:
            args.append(arg) # it's supposed to be a path.
        i += 1

    # Get input directory
    if args:
        input_dir = Path(args[0])
    else:
        input_dir = Path.cwd()
    
    if not input_dir.exists():
        print(f"Error: Directory '{input_dir}' does not exist")
        return 1
    
    print(f"\nInput directory: {input_dir.absolute()}")
    if USE_DITHERING:
        print("Dithering: ENABLED (better for screentones/gradients, use --no-dither to enable)")
    else:
        print("Dithering: DISABLED")
    
    # Determine number of threads
    max_workers = min(4, os.cpu_count() or 1)  # Use up to 4 threads
    print(f"Threads: {max_workers} (parallel processing)")
    
    # Create output and temp directories
    output_dir = input_dir / "xtc_output"
    temp_dir = input_dir / ".temp_png"
    
    output_dir.mkdir(exist_ok=True)
    temp_dir.mkdir(exist_ok=True)
    
    # Find all CBZ files (including in subdirectories)
    cbz_files = []
    
    # Check current directory
    cbz_files.extend(sorted(input_dir.glob("*.cbz")))
    cbz_files.extend(sorted(input_dir.glob("*.CBZ")))
    
    # Only check subdirectories if no CBZ files found in current directory
    if not cbz_files:
        for subdir in input_dir.iterdir():
            if subdir.is_dir() and subdir.name not in ["xtc_output", ".temp_png"]:
                cbz_files.extend(sorted(subdir.glob("*.cbz")))
                cbz_files.extend(sorted(subdir.glob("*.CBZ")))
    
    # Remove any duplicates (shouldn't happen now, but just in case)
    cbz_files = list(dict.fromkeys(cbz_files))
    
    if not cbz_files:
        print(f"\nNo CBZ files found in '{input_dir}' or its subdirectories")
        return 1
    
    print(f"\nFound {len(cbz_files)} CBZ file(s)")
    print(f"Output directory: {output_dir.absolute()}")
    print(f"Temp directory: {temp_dir.absolute()}")
    if clean_temp:
        print("Clean mode: Temporary files will be deleted after conversion")
    print("-" * 60)
    
    # Verify png2xtc.py exists
    png2xtc_path = find_png2xtc()
    if not png2xtc_path:
        print(f"\n✗ Error: png2xtc.py not found")
        print(f"\nThe epub2xtc library is required to convert PNG to XTC format.")
        print(f"Repository: https://github.com/jonasdiemer/epub2xtc")
        
        # Ask user if they want to clone it
        try:
            response = input("\nWould you like to clone epub2xtc now? (Y/n): ").strip().lower()
            
            if response in ['y', 'yes', '']:
                # Determine where to clone
                clone_dir = Path(__file__).parent / "epub2xtc"
                
                print(f"\nCloning to: {clone_dir}")
                print("Running: git clone https://github.com/jonasdiemer/epub2xtc.git")
                
                result = subprocess.run(
                    ["git", "clone", "https://github.com/jonasdiemer/epub2xtc.git", str(clone_dir)],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print("✓ Successfully cloned epub2xtc!")
                    print("\nPlease run cbz2xtc again.")
                    return 0
                else:
                    print(f"✗ Failed to clone: {result.stderr}")
                    print("\nPlease clone manually:")
                    print("  git clone https://github.com/jonasdiemer/epub2xtc.git")
                    return 1
            else:
                print("\nPlease install epub2xtc manually:")
                print("  git clone https://github.com/jonasdiemer/epub2xtc.git")
                print("\nOr set PNG2XTC_PATH environment variable to the location of png2xtc.py")
                return 1
                
        except KeyboardInterrupt:
            print("\n\nCancelled by user.")
            return 1
        except Exception as e:
            print(f"\nError: {e}")
            print("\nPlease install epub2xtc manually:")
            print("  git clone https://github.com/jonasdiemer/epub2xtc.git")
            return 1
    
    print(f"Using png2xtc.py from: {png2xtc_path.parent}")
    
    # Process files with multithreading
    start_time = time.time()
    success_count = 0
    total_time = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_cbz = {
            executor.submit(process_cbz_file, cbz_file, output_dir, temp_dir, clean_temp, idx, len(cbz_files)): cbz_file
            for idx, cbz_file in enumerate(cbz_files, 1)
        }
        
        # Process results as they complete
        for future in as_completed(future_to_cbz):
            success, filename, elapsed = future.result()
            if success:
                success_count += 1
                total_time += elapsed
                avg_time = total_time / success_count
                remaining = (len(cbz_files) - success_count) * avg_time
                print(f"  ⏱  {elapsed:.1f}s | Est. remaining: {remaining/60:.1f}min")
    
    elapsed_total = time.time() - start_time
    
    print("-" * 60)
    print(f"\nCompleted! Successfully converted {success_count}/{len(cbz_files)} files")
    print(f"Total time: {elapsed_total/60:.1f} minutes")
    print(f"Average: {elapsed_total/len(cbz_files):.1f}s per file")
    print(f"\nXTC files are in: {output_dir.absolute()}")
    
    # Clean up temp directory if empty or if clean mode
    if clean_temp:
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                print("Temporary files cleaned up")
        except:
            pass
    else:
        print(f"Temporary PNG files are in: {temp_dir.absolute()}")
        print("(Run with --clean flag to auto-delete temp files)")
    
    print("\nTransfer the .xtc files to your XTEink X4!")
    
    return 0 if success_count == len(cbz_files) else 1


if __name__ == "__main__":
    sys.exit(main())