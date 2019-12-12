from argparse import ArgumentError
import csv
from keras.optimizers import Adam
from keras.callbacks import Callback, ModelCheckpoint
from keras.engine.saving import load_model
from keras.preprocessing.image import ImageDataGenerator
from natsort import natsorted
import re


def tune(net, epochs, train_dir, test_dir, out_dir, batch_size=None, image_size=None, persistence=None):
    if not image_size:
        from hw2.data import ImageSize
        image_size = ImageSize(244, 244)
    if persistence is None:
        persistence = []

    try:
        model_file = natsorted([f for f in (out_dir / "models").glob(f"{net}-*.h5")
                                if re.match(fr"{net}-\d+\.h5", f.name)])[-1]
        initial_epoch = int(re.match(fr"{net}-(\d+)\.h5", model_file.name).group(1))
        model = load_model(model_file)
        print(f"Loaded model {model_file.name}")

    except IndexError:
        initial_epoch = 0
        num_classes = len([c for c in train_dir.iterdir() if c.is_dir()])
        (out_dir / "models").mkdir(exist_ok=True, parents=True)
        if net == "inception":
            from hw2.models import inception
            model = inception(image_size, num_classes)
        elif net == "resnet50":
            from hw2.models import resnet50
            model = resnet50(image_size, num_classes)
        elif net == "vgg16":
            from hw2.models import vgg16
            model = vgg16(image_size, num_classes)
        else:
            raise ArgumentError(f"Unknown network '{net}'")

    # Show model summary
    model.summary()

    # Read images and augment data
    train_datagen = ImageDataGenerator(fill_mode="nearest",
                                       height_shift_range=0.2,
                                       horizontal_flip=True,
                                       rescale=1. / 255,
                                       rotation_range=20,
                                       shear_range=0.2,
                                       width_shift_range=0.2)
    validation_datagen = ImageDataGenerator(rescale=1. / 255)

    # Use batch_size only if it is a meaningful value
    train_generator = train_datagen.flow_from_directory(train_dir,
                                                        target_size=image_size.dimensions(),
                                                        class_mode='categorical',
                                                        **{k: v for k, v in {"batch_size": batch_size}.items() if v})
    validation_generator = validation_datagen.flow_from_directory(test_dir,
                                                                  target_size=image_size.dimensions(),
                                                                  class_mode='categorical',
                                                                  shuffle=False,
                                                                  **{k: v for k, v in {"batch_size": batch_size}.items()
                                                                     if v})

    model.compile(loss='categorical_crossentropy',
                  optimizer=Adam(),
                  metrics=['acc'])

    # Define callbacks
    history_checkpoint = HistoryCheckPoint(net, out_dir)
    callbacks_list = [history_checkpoint]
    if "best" in persistence:
        callbacks_list.append(ModelCheckpoint((out_dir / "models" / f"{net}-best.h5").as_posix(), period=1,
                                              save_best_only=True, verbose=1))
    if "all" in persistence:
        callbacks_list.append(ModelCheckpoint((out_dir / "models" / (net + "-{epoch:02d}.h5")).as_posix(), period=1,
                                              verbose=1))
    elif "last" in persistence:
        callbacks_list.append(ModelCheckpoint((out_dir / "models" / f"{net}.h5").as_posix(), period=1, verbose=1))

    # Train model
    model.fit_generator(train_generator,
                        callbacks=callbacks_list,
                        epochs=epochs,
                        initial_epoch=initial_epoch,
                        steps_per_epoch=train_generator.samples / train_generator.batch_size,
                        validation_data=validation_generator,
                        validation_steps=validation_generator.samples / validation_generator.batch_size,
                        verbose=1)

    return history_checkpoint.history


class HistoryCheckPoint(Callback):
    metrics = ["acc", "val_acc", "loss", "val_loss"]

    def __init__(self, net, out_dir):
        super().__init__()
        self.history = out_dir / f"{net}.history"

        if not self.history.is_file():
            with open(self.history, "w", newline='') as fout:
                writer = csv.DictWriter(fout, fieldnames=HistoryCheckPoint.metrics)
                writer.writeheader()

    def on_epoch_end(self, epoch, logs=None):
        with open(self.history, "a", newline='') as fout:
            csv.DictWriter(fout, extrasaction="ignore", fieldnames=HistoryCheckPoint.metrics, restval=0) \
                .writerow(logs)
