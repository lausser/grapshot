import asyncio
import yaml
import os
import sys
import re
import time
import logging
import tracemalloc
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright, expect


async def main(config):
    """
        global:
            debug
            viewport_width = width of the browser viewport
            postprocess = postprocess the screenshot
            colors = reduce the color palette
            colormode = P|RGB|RGBA
            resize = shrink the image width (and calculate new heigth)
            resize_width = new width (800 default)
            baseurl = url up to /d
            loadwait = seconds to wait until there is no more loading wheel
        per dashboard:
            url = everything after the /d/....
            name = description, default is the dashboards title
    """
    if "DISPLAY" in os.environ and os.environ["DISPLAY"]:
        logging.debug("DISPLAY is {}".format(os.environ["DISPLAY"]))
        headless = False
        for line in os.popen("xdpyinfo").readlines():
            if "dimensions" in line:
                logging.debug(line)
    else:
        headless = True
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            ignore_https_errors=True,
        )
        context.set_default_timeout(120000)
        context.set_default_navigation_timeout(120000)
        page = await context.new_page()
        await page.set_extra_http_headers({"X-WEBAUTH-USER": "omdadmin"})
        page.set_default_timeout(120000)
        page.set_default_navigation_timeout(120000)
        logging.debug("initial viewport {}x{}".format(page.viewport_size["width"], page.viewport_size["height"]))
        load_wait = int(config["load_wait"])*1000 if "load_wait" in config else 10000
        #viewport_width = 1632
        viewport_width = int(config["viewport_width"]) if "viewport_width" in config else 1280
        viewport_height = 1024
        for dashboard in config["dashboards"]:
            if not dashboard["url"]:
                continue
            url = config["baseurl"]+dashboard["url"]
            logging.info("processing url {}".format(url))
            # postpone the next refresh
            url = re.sub(r'&refresh=\d+.', '', url)
            if not "?" in url:
                url += "?refresh=1h"
            else:
                url += "&refresh=1h"
            # we have a big screen so that everything fits into the viewport
            await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
            logging.debug("viewport size is {}x{}".format(viewport_width, viewport_height))
            await page.goto(url, wait_until='networkidle')
            logging.debug("network is idle")

            try:
                grafana_version = await page.locator("text=/Grafana\sv[\d\.]+\s/i").all_text_contents()
                grafana_version = grafana_version[0]
                # Grafana v7.5.13 ()
                logging.debug("Detected version {}".format(grafana_version))
                grafana_version = re.match(r'[^\d\.]+([\d\.]+)', grafana_version).group(1)
            except:
                try:
                    whole_page = await page.content()
                    version_m = re.search(r'(Grafana\sv([\d\.]+))', whole_page)
                    if version_m:
                        grafana_version = version_m.group(2)
                        logging.debug("Detected version {}".format(grafana_version))
                except Exception as e:
                    print(e)
                    logging.critical("Could not find the Grafana version")
                    grafana_version = "0.0"

            # If the user did not set a name for a dashboard in the file
            # dashboards.yml, we name use the dashboard title shown
            # in the browser to create a recognisable filename.
            # ! it looks like the title is empty when the page is opened
            # in a headless browser.
            title = await page.title()
            logging.debug("Dashboard title is {}".format(title))
            filetype = config["filetype"] if "filetype" in config else "png"
            #time.sleep(1000)
            if "name" in dashboard and dashboard["name"]:
                name = dashboard["name"].replace(" ", "_").replace("/", "_")
                filename = config["output"]+"/"+dashboard["signature"]+"_"+name+"."+filetype
            else:
                title = title.rstrip(" - Grafana").replace(" ", "_").replace("/", "_")
                if not title:
                    title = re.match(r'^.*/d/[^/]+/(.*)', url).group(1)
                    if "?" in title:
                        title = title.split("?")[0]
                    title = re.sub("[^0-9a-zA-Z-]+", "_", title)
                filename = config["output"]+"/"+dashboard["signature"]+"_"+title+"."+filetype

            if grafana_version.startswith("9"):
                #    scrollbar-view
                #?     dashboard-content - scrollbar-view without some margin
                #      submenu-controls - dropdown-variables (optional!)
                #      react-grid-layout - the panels
                #loc_div_dashboard_container = page.locator("div.dashboard-container")
                #loc_div_page_toolbar = page.locator("div.page-toolbar")
                #loc_div_dashboard_scroll = page.locator("div.dashboard-scroll")
                #loc_div_dashboard_content = page.locator("div.dashboard-content")
                loc_div_react_grid_layout = page.locator("div.react-grid-layout")
                loc_div_react_grid_layout_parent = page.locator("div.react-grid-layout >> xpath=..")
                logging.debug(loc_div_react_grid_layout)
                logging.debug(loc_div_react_grid_layout_parent)
                #div_dashboard_container = await loc_div_dashboard_container.bounding_box()
                #div_page_toolbar = await loc_div_page_toolbar.bounding_box()
                #div_dashboard_scroll = await loc_div_dashboard_scroll.bounding_box()
                #div_dashboard_content = await loc_div_dashboard_content.bounding_box()
                div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                logging.debug("div_react_grid_layout (all the panels) height is {}".format(div_react_grid_layout["height"]))
                # expect that there is at least one progress/loading-wheel
                # immediately after a page has loaded.
                loc_loading_wheel = page.locator("div.panel-loading")
                try:
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("initially found {} wheels".format(num_loading_wheel))
                    await expect(loc_loading_wheel).not_to_have_count(0, timeout=1000)
                except:
                    logging.debug("no wheel appeared")
                    # maybe loading was very quick and is already done
                    pass
                pass
            elif grafana_version.startswith("7"):
                # we have a hierarchy of divs in this order:
                # scroll-canvas - the whole page without left menu
                #  dashboard-container -
                #   page-toolbar - folder/title, timerange, refresh-interval
                #   dashboard-scroll - dropdown-variables and panels
                #    scrollbar-view
                #     dashboard-content - scrollbar-view without some margin
                #      submenu-controls - dropdown-variables (optional!)
                #      react-grid-layout - the panels
                # First there will be a lot of blank space after the panels. The div
                # react-grid-layout will be the first element in the hierarchy which
                # has a reasonable height (dashboard-content for example is as high as
                # the whole viewport, including all the blank space)
                loc_div_dashboard_container = page.locator("div.dashboard-container")
                loc_div_page_toolbar = page.locator("div.page-toolbar")
                loc_div_dashboard_scroll = page.locator("div.dashboard-scroll")
                loc_div_dashboard_content = page.locator("div.dashboard-content")
                loc_div_react_grid_layout = page.locator("div.react-grid-layout")
                div_dashboard_container = await loc_div_dashboard_container.bounding_box()
                div_page_toolbar = await loc_div_page_toolbar.bounding_box()
                div_dashboard_scroll = await loc_div_dashboard_scroll.bounding_box()
                div_dashboard_content = await loc_div_dashboard_content.bounding_box()
                div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                logging.debug("div_react_grid_layout (all the panels) height is {}".format(div_react_grid_layout["height"]))
                if True:
                    logging.debug("div_dashboard_container {} {}".format(div_dashboard_container["height"], div_dashboard_container["y"]))
                    logging.debug(" div_page_toolbar {} {}".format(div_page_toolbar["height"], div_page_toolbar["y"]))
                    logging.debug(" div_dashboard_scroll {} {}".format(div_dashboard_scroll["height"], div_dashboard_scroll["y"]))
                    logging.debug("  div_dashboard_content {} {}".format(div_dashboard_content["height"], div_dashboard_content["y"]))
                    logging.debug("   div_react_grid_layout {} {}".format(div_react_grid_layout["height"], div_react_grid_layout["y"]))

                # expect that there is at least one progress/loading-wheel
                # immediately after a page has loaded.
                loc_loading_wheel = page.locator("div.panel-loading")
                try:
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("initially found {} wheels".format(num_loading_wheel))
                    await expect(loc_loading_wheel).not_to_have_count(0, timeout=1000)
                except:
                    logging.debug("no wheel appeared")
                    # maybe loading was very quick and is already done
                    pass
                # now expect all wheels to disappear.
                try:
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("found {} wheels".format(num_loading_wheel))
                    await expect(loc_loading_wheel).to_have_count(0, timeout=load_wait)
                    logging.debug("no more wheels")
                except:
                    # loading took to much time
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("still found {} wheels after {}s".format(num_loading_wheel, load_wait/1000))
                    pass

                await loc_div_dashboard_scroll.hover()
                while div_react_grid_layout["height"]+div_react_grid_layout["y"] >= div_dashboard_container["height"]:
                    logging.debug("scroll down {} pixel...".format(int(viewport_height/2)))
                    await page.mouse.wheel(0, int(viewport_height/2))
                    try:
                        await expect(loc_loading_wheel).to_have_count(0, timeout=load_wait)
                        logging.debug("no loading wheel found")
                    except:
                        num_loading_wheel = await loc_loading_wheel.count()
                        logging.info("still {} wheels found, wait for network idle".format(num_loading_wheel))
                        pass
                    await page.wait_for_load_state("networkidle")

                    div_dashboard_container = await loc_div_dashboard_container.bounding_box()
                    div_page_toolbar = await loc_div_page_toolbar.bounding_box()
                    div_dashboard_scroll = await loc_div_dashboard_scroll.bounding_box()
                    div_dashboard_content = await loc_div_dashboard_content.bounding_box()
                    div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                    logging.debug("div_dashboard_container {} {}".format(div_dashboard_container["height"], div_dashboard_container["y"]))
                    logging.debug(" div_page_toolbar {} {}".format(div_page_toolbar["height"], div_page_toolbar["y"]))
                    logging.debug(" div_dashboard_scroll {} {}".format(div_dashboard_scroll["height"], div_dashboard_scroll["y"]))
                    logging.debug("  div_dashboard_content {} {}".format(div_dashboard_content["height"], div_dashboard_content["y"]))
                    logging.debug("   div_react_grid_layout {} {}".format(div_react_grid_layout["height"], div_react_grid_layout["y"]))
                    offset = div_react_grid_layout["height"]+div_react_grid_layout["y"]
                    logging.debug("offset is {}  ... {}".format(offset, div_dashboard_container["height"]))

                # Based on react-grid-layout plus the header heights
                # we will resize the viewport so that the viewport is only
                # as big as necessary but big enough to show all the panels.
                # (plus a few pixels more, 2*toolbar height)
                div_page_toolbar = await loc_div_page_toolbar.bounding_box()
                try:
                    loc_div_submenu_controls = await page.wait_for_selector("div.submenu-controls")
                    logging.debug("submenu-controls found")
                    div_submenu_controls = await loc_div_submenu_controls.bounding_box()
                except:
                    div_submenu_controls = { "height": 0 }
                div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                new_height = div_react_grid_layout["height"] + div_submenu_controls["height"] + div_page_toolbar["height"] * 2
                await page.set_viewport_size({"width": viewport_width, "height": new_height})
                logging.debug("adjusted viewport size to {}x{}".format(viewport_width, new_height))

                await loc_div_dashboard_container.screenshot(path=filename)
                if "pdf" in config and config["pdf"] == True:
                    await page.pdf(path=filename+".pdf")
                logging.info("Saved screenshot to {}".format(filename))
                filesize1 = os.stat(filename).st_size
                image = Image.open(filename)
                width, height = image.size
                logging.debug("filesize is {}".format(filesize1))
                logging.debug("image mode is {}, dimensions {}x{}".format(image.mode, width, height))
                if "postprocess" in config and config["postprocess"]:
                    # PDF conversion may fail if the images are too big. Reduce
                    # the size.
                    colormode = config["colormode"] if "colormode" in config else "RGB"
                    colors = int(config["colors"]) if "colors" in config else 256
                    if image.mode != colormode and colors != "true":
                        logging.debug("converting image to colormode {} with {} colors".format(colormode, colors))
                        image = image.convert(colormode, palette=Image.ADAPTIVE, colors=colors)
                    elif image.mode != colormode:
                        logging.debug("converting image to colormode {}".format(colormode))
                        image = image.convert(colormode)
                    elif colors != "true":
                        logging.debug("converting image to {} colors".format(colors))
                        image = image.convert(image.mode, palette=Image.ADAPTIVE, colors=colors)
                    width, height = image.size
                    if "resize" in config and config["resize"]:
                        new_width = int(config["resize_width"]) if "resize_width" in config else int(width/2)
                        new_height = int(new_width * height / width)
                        #image.resize((new_width, new_height)).save(filename, optimize=True)
                        image.resize((new_width, new_height)).save(filename)
                    else:
                        image.save(filename)
                    width, height = image.size
                    logging.debug("now image mode is {}, dimensions {}x{}".format(image.mode, width, height))
                    filesize2 = os.stat(filename).st_size
                    logging.debug("reduced the filesize from {} to {}".format(filesize1, filesize2))
            elif grafana_version.startswith("10"):
                # we have a hierarchy of divs in this order:
                # div id="reactRoot"
                #  div class="grafana-app"
                #   div class="main-view"
                #    div id="pageContent"
                #    -> rechter hauptteil. menue ist ein paralleles div zu diesem
                #    ...
                #     div class="scrollbar-view"
                #     -< 1627x952
                #     -> links oben klicken, dann mausradscrollen moeglich
                #        oder hover
                #      noch ein div, dann
                #       <header data-test-id="data-testid Dashboard navigation"
                #       <section aria-label="Dashboard submenu" <--
                #       -> dashboard header
                #       div style="flex: 1 1 auto" <---
                #       ... darunter div class="react-grid-layout"
                #         -> 1587x1284
                #         -> paneltitel und panel...  hat height und width
                #     div class="track-horizontal"
                #     div class="track-vertical" -> scrollbar
                #time.sleep(100001)

                logging.debug("locate div.grafana-app")
                loc_div_grafana_app = page.locator("div.grafana-app")
                div_grafana_app = await loc_div_grafana_app.bounding_box()

                logging.debug("locate #pageContent")
                loc_div_page_content = page.locator("#pageContent")
                div_page_content = await loc_div_page_content.bounding_box()

                logging.debug("locate section Dashboard submenu")
                loc_section_dashboard_submenu = page.locator("section[aria-label='Dashboard submenu']")
                section_dashboard_submenu = await loc_section_dashboard_submenu.bounding_box()

                logging.debug("locate header")
                loc_header = page.get_by_test_id("data-testid Dashboard navigation")
                header = await loc_header.bounding_box()

                logging.debug("locate main with section and div")
                loc_main = loc_header.locator('xpath=..')
                main = await loc_main.bounding_box()

                # main contains header section and a div
                # its parent is a div scrollbar-view
                logging.debug("locate div.scrollbar-view under main")
                #loc_div_scrollbar_view = page.locator("div.scrollbar-view")
                loc_div_scrollbar_view = loc_main.locator("xpath=..")
                div_scrollbar_view = await loc_div_scrollbar_view.bounding_box()


                logging.debug("box div.react-grid-layout")
                loc_div_react_grid_layout = loc_main.locator("div.react-grid-layout")
                div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()

                section_dashboard_submenu_height = section_dashboard_submenu["height"]
                logging.debug("div_react_grid_layout (all the panels) height is {}".format(div_react_grid_layout["height"]))
                if True:
                    logging.debug("div_scrollbar_view {} {}".format(div_scrollbar_view["height"], div_scrollbar_view["y"]))
                    logging.debug("   div_react_grid_layout {} {}".format(div_react_grid_layout["height"], div_react_grid_layout["y"]))

                # expect that there is at least one progress/loading-wheel
                # immediately after a page has loaded.
                loc_loading_wheel = page.locator("div.panel-loading")
                try:
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("initially found {} wheels".format(num_loading_wheel))
                    await expect(loc_loading_wheel).not_to_have_count(0, timeout=1000)
                except:
                    logging.debug("no wheel appeared")
                    # maybe loading was very quick and is already done
                    pass
                # now expect all wheels to disappear.
                try:
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("found {} wheels".format(num_loading_wheel))
                    await expect(loc_loading_wheel).to_have_count(0, timeout=load_wait)
                    logging.debug("no more wheels")
                except:
                    # loading took to much time
                    num_loading_wheel = await loc_loading_wheel.count()
                    logging.debug("still found {} wheels after {}s".format(num_loading_wheel, load_wait/1000))
                    pass

                await loc_div_scrollbar_view.hover()

                # on a wheel down event, this happens:
                # div_scrollbar_view height and y always stay the same
                #  because it's a bit more than the browser size does not move
                #  height 952 and y 80 mean: bottom visible area is 1032
                # div_react_grid_layout height stays biig and y decreases.
                #  it even gets negative, because the upper edge moves above the
                #  visibe window. height 1284 and y 136 mean: bottom is at 1420
                #  (136 is probably the height of the variable/button row)
                # now we scroll until bottom 1420 decreases to 1032, so that
                # bottom of visible area and bottom of dashboard touch
                div_scrollbar_view_bottom = div_scrollbar_view["y"] + div_scrollbar_view["height"]
                div_react_grid_layout_bottom = div_react_grid_layout["y"] + div_react_grid_layout["height"]
                logging.debug("div_scrollbar_view_bottom {}".format(div_scrollbar_view_bottom))
                logging.debug("div_react_grid_layout_bottom {}".format(div_react_grid_layout_bottom))
                logging.debug("=--{}---   --{}--".format(div_scrollbar_view_bottom, div_react_grid_layout_bottom))
                # offset is where content starts
                div_scrollbar_view_offset = div_scrollbar_view["y"]
                scroll_distance = int(div_scrollbar_view["height"] / 3)
                #scroll_distance = 2
                while div_scrollbar_view_bottom <= div_react_grid_layout_bottom:

                    await page.mouse.wheel(0, scroll_distance)
                    try:
                        await expect(loc_loading_wheel).to_have_count(0, timeout=load_wait)
                        logging.debug("no loading wheel found")
                    except:
                        num_loading_wheel = await loc_loading_wheel.count()
                        logging.info("still {} wheels found, wait for network idle".format(num_loading_wheel))
                        pass
                    await page.wait_for_load_state("networkidle")

                    div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                    div_react_grid_layout_bottom = div_react_grid_layout["y"] + div_react_grid_layout["height"]
                    logging.debug("---{}---   --{}--".format(div_scrollbar_view_bottom, div_react_grid_layout_bottom))


                # Based on react-grid-layout plus the header heights
                # we will resize the viewport so that the viewport is only
                # as big as necessary but big enough to show all the panels.
                # (plus a few pixels more, 2*toolbar height)
#                div_page_toolbar = await loc_div_page_toolbar.bounding_box()
#                try:
#                    loc_div_submenu_controls = await page.wait_for_selector("div.submenu-controls")
#                    logging.debug("submenu-controls found")
#                    div_submenu_controls = await loc_div_submenu_controls.bounding_box()
#                except:
#                    div_submenu_controls = { "height": 0 }
#                div_react_grid_layout = await loc_div_react_grid_layout.bounding_box()
                new_height = div_react_grid_layout["height"] + section_dashboard_submenu_height * 4
                await page.set_viewport_size({"width": viewport_width, "height": new_height})
                logging.debug("adjusted viewport size to {}x{}".format(viewport_width, new_height))


                await loc_div_scrollbar_view.screenshot(path=filename)
                if "pdf" in config and config["pdf"] == True:
                    await page.pdf(path=filename+".pdf")
                logging.info("Saved screenshot to {}".format(filename))
                filesize1 = os.stat(filename).st_size
                image = Image.open(filename)
                width, height = image.size
                logging.debug("filesize is {}".format(filesize1))
                logging.debug("image mode is {}, dimensions {}x{}".format(image.mode, width, height))
                if "postprocess" in config and config["postprocess"]:
                    # PDF conversion may fail if the images are too big. Reduce
                    # the size.
                    colormode = config["colormode"] if "colormode" in config else "RGB"
                    colors = int(config["colors"]) if "colors" in config else 256
                    if image.mode != colormode and colors != "true":
                        logging.debug("converting image to colormode {} with {} colors".format(colormode, colors))
                        image = image.convert(colormode, palette=Image.ADAPTIVE, colors=colors)
                    elif image.mode != colormode:
                        logging.debug("converting image to colormode {}".format(colormode))
                        image = image.convert(colormode)
                    elif colors != "true":
                        logging.debug("converting image to {} colors".format(colors))
                        image = image.convert(image.mode, palette=Image.ADAPTIVE, colors=colors)
                    width, height = image.size
                    if "resize" in config and config["resize"]:
                        new_width = int(config["resize_width"]) if "resize_width" in config else int(width/2)
                        new_height = int(new_width * height / width)
                        #image.resize((new_width, new_height)).save(filename, optimize=True)
                        image.resize((new_width, new_height)).save(filename)
                    else:
                        image.save(filename)
                    width, height = image.size
                    logging.debug("now image mode is {}, dimensions {}x{}".format(image.mode, width, height))
                    filesize2 = os.stat(filename).st_size
                    logging.debug("reduced the filesize from {} to {}".format(filesize1, filesize2))

                
            else:
                await page.screenshot(path="/output/screen.png")
                # Write the error message to an image file, so that it later
                # can be shown in a pdf report.
                logging.critical("Version {} of Grafana is not supported".format(grafana_version))
            time.sleep(10)

        await browser.close()
        logging.debug("Browser closed")

if __name__ == "__main__":
    config_file = os.environ.get("GRAPSHOT_DASHBOARDS", None)
    try:
        with open(config_file) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
            if "debug" in config and config["debug"]:
                logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG,
                    handlers=[logging.StreamHandler(), logging.FileHandler(config["output"]+"/grapshot.log")])
                with open("/root/VERSION") as f:
                    version = f.read().strip()
                    logging.info("grapshot version {}".format(version))
            else:
                logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)
            asyncio.run(main(config))
    except Exception as e:
        print(e, file=sys.stderr)
        logging.critical(str(e))

