// SPDX-License-Identifier: GPL-2.0-only
/*
 * Experimental V851S/RTL8733BS Linux 7.2.7 board-control compatibility layer.
 * COMPILE TEST ONLY — DO NOT LOAD ON A REAL M6.
 *
 * No M6 board DTB/GPIOs are known. No DT node is provided that can match this
 * driver. There is deliberately no fallback GPIO, MMC host number or address.
 * This only sketches the three legacy Sunxi calls using standard Linux APIs.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/err.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/gpio/consumer.h>
#include <linux/regulator/consumer.h>
#include <linux/mmc/host.h>
#include <linux/mutex.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/string.h>

struct m6_wifi_board {
	struct device *dev;
	struct gpio_desc *regon;
	struct gpio_desc *chip_en;
	struct regulator *vdd;
	struct device_node *mmc_node;
	u32 bus_index;
	bool powered;
};

static DEFINE_MUTEX(m6_wifi_lock);
static struct m6_wifi_board *m6_wifi_active;

/* API name and return convention of the legacy vendor module. */
int sunxi_wlan_get_bus_index(void)
{
	int ret = -ENODEV;

	mutex_lock(&m6_wifi_lock);
	if (m6_wifi_active)
		ret = (int)m6_wifi_active->bus_index;
	mutex_unlock(&m6_wifi_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(sunxi_wlan_get_bus_index);

/* The original vendor function returns void. Do not report fictitious success. */
void sunxi_wlan_set_power(int on)
{
	struct m6_wifi_board *b;
	int ret;

	mutex_lock(&m6_wifi_lock);
	b = m6_wifi_active;
	if (!b)
		goto done;
	if (!!on == b->powered)
		goto done;

	if (on) {
		if (b->vdd) {
			ret = regulator_enable(b->vdd);
			if (ret) {
				dev_err(b->dev, "research Wi-Fi regulator enable failed: %d\n", ret);
				goto done;
			}
		}
		gpiod_set_value_cansleep(b->chip_en, 1);
		msleep(10);
		gpiod_set_value_cansleep(b->regon, 1);
		b->powered = true;
	} else {
		gpiod_set_value_cansleep(b->regon, 0);
		gpiod_set_value_cansleep(b->chip_en, 0);
		if (b->vdd)
			regulator_disable(b->vdd);
		b->powered = false;
	}
done:
	mutex_unlock(&m6_wifi_lock);
}
EXPORT_SYMBOL_GPL(sunxi_wlan_set_power);

static int m6_mmc_find_host(struct device *dev, void *ptr)
{
	struct mmc_host **found = ptr;

	if (strncmp(dev_name(dev), "mmc", 3))
		return 0;
	get_device(dev);
	*found = container_of(dev, struct mmc_host, class_dev);
	return 1;
}

/* MMC host is selected ONLY by a verified DT phandle, never by a guessed ID. */
void sunxi_mmc_rescan_card(unsigned int id)
{
	struct device_node *node = NULL;
	struct platform_device *pdev;
	struct mmc_host *host = NULL;

	mutex_lock(&m6_wifi_lock);
	if (m6_wifi_active && id == m6_wifi_active->bus_index)
		node = of_node_get(m6_wifi_active->mmc_node);
	mutex_unlock(&m6_wifi_lock);
	if (!node)
		return;

	pdev = of_find_device_by_node(node);
	of_node_put(node);
	if (!pdev)
		return;
	device_for_each_child(&pdev->dev, &host, m6_mmc_find_host);
	put_device(&pdev->dev);
	if (!host)
		return;
	mmc_detect_change(host, 0);
	put_device(&host->class_dev);
}
EXPORT_SYMBOL_GPL(sunxi_mmc_rescan_card);

static int m6_wifi_probe(struct platform_device *pdev)
{
	struct m6_wifi_board *b;
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	int ret;

	/* Intentional double gate: no M6 DTB has been independently verified. */
	if (!np || !of_property_read_bool(np, "research,board-verified"))
		return -ENODEV;
	b = devm_kzalloc(dev, sizeof(*b), GFP_KERNEL);
	if (!b)
		return -ENOMEM;
	b->dev = dev;
	ret = of_property_read_u32(np, "wlan-bus-index", &b->bus_index);
	if (ret || b->bus_index > 2)
		return -EINVAL;
	b->mmc_node = of_parse_phandle(np, "mmc-host", 0);
	if (!b->mmc_node)
		return -EINVAL;
	b->regon = devm_gpiod_get(dev, "wlan-regon", GPIOD_OUT_LOW);
	if (IS_ERR(b->regon)) {
		ret = PTR_ERR(b->regon);
		goto err_node;
	}
	b->chip_en = devm_gpiod_get(dev, "chip-en", GPIOD_OUT_LOW);
	if (IS_ERR(b->chip_en)) {
		ret = PTR_ERR(b->chip_en);
		goto err_node;
	}
	b->vdd = devm_regulator_get_optional(dev, "wlan");
	if (IS_ERR(b->vdd)) {
		ret = PTR_ERR(b->vdd);
		if (ret != -ENODEV)
			goto err_node;
		b->vdd = NULL;
	}
	mutex_lock(&m6_wifi_lock);
	if (m6_wifi_active) {
		mutex_unlock(&m6_wifi_lock);
		ret = -EBUSY;
		goto err_node;
	}
	m6_wifi_active = b;
	mutex_unlock(&m6_wifi_lock);
	platform_set_drvdata(pdev, b);
	dev_warn(dev, "research-only board ABI present; not validated on M6\n");
	return 0;
err_node:
	of_node_put(b->mmc_node);
	return ret;
}

static void m6_wifi_remove(struct platform_device *pdev)
{
	struct m6_wifi_board *b = platform_get_drvdata(pdev);

	/* A disabled-by-default research device: no in-field unload is supported. */
	mutex_lock(&m6_wifi_lock);
	if (m6_wifi_active == b) {
		if (b->powered) {
			gpiod_set_value_cansleep(b->regon, 0);
			gpiod_set_value_cansleep(b->chip_en, 0);
			if (b->vdd)
				regulator_disable(b->vdd);
			b->powered = false;
		}
		m6_wifi_active = NULL;
	}
	mutex_unlock(&m6_wifi_lock);
	of_node_put(b->mmc_node);
}

static const struct of_device_id m6_wifi_of_match[] = {
	{ .compatible = "research,v851s-lybox-rtl8-wifi-verified" },
	{ }
};
MODULE_DEVICE_TABLE(of, m6_wifi_of_match);

static struct platform_driver m6_wifi_driver = {
	.probe = m6_wifi_probe,
	.remove = m6_wifi_remove,
	.driver = {
		.name = "m6-sunxi-wifi-research-v16",
		.of_match_table = m6_wifi_of_match,
	},
};
module_platform_driver(m6_wifi_driver);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Offline research only: Sunxi legacy Wi-Fi platform ABI, NOT M6-verified");
MODULE_AUTHOR("M6 V851S independent research");
